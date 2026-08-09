from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FULL_SHA = re.compile(r"[0-9a-f]{40}")
BYTE_UNITS = {
    "B": 1,
    "kB": 1_000,
    "KB": 1_000,
    "KiB": 1024,
    "MB": 1_000_000,
    "MiB": 1024**2,
    "GB": 1_000_000_000,
    "GiB": 1024**3,
}
FARGATE_MEMORY_BY_CPU = {
    256: frozenset(range(512, 2049, 512)),
    512: frozenset(range(1024, 4097, 1024)),
    1024: frozenset(range(2048, 8193, 1024)),
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def run_json(command: list[str]) -> Any:
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return json.loads(result.stdout)


def parse_memory_bytes(value: str) -> int:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)\s*", value)
    if match is None or match.group(2) not in BYTE_UNITS:
        raise ValueError("Docker reported an unsupported memory value.")
    return round(float(match.group(1)) * BYTE_UNITS[match.group(2)])


def parse_percentage(value: str) -> float:
    if not value.endswith("%"):
        raise ValueError("Docker reported an unsupported percentage value.")
    return float(value[:-1])


def load_configuration(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("schemaVersion") != 1:
        raise ValueError("Sizing configuration has an unsupported schema.")
    measurement = document.get("measurement")
    tasks = document.get("tasks")
    processes = document.get("processes")
    if not all(isinstance(value, dict) for value in (measurement, tasks, processes)):
        raise ValueError("Sizing configuration is incomplete.")
    if not isinstance(measurement.get("workload"), str) or not isinstance(
        measurement.get("uncertainty"), str
    ):
        raise ValueError("Sizing workload and uncertainty must be explicit.")
    minimum_samples = measurement.get("minimumSamples")
    interval = measurement.get("sampleIntervalSeconds")
    headroom = measurement.get("minimumHeadroomFraction")
    if (
        not isinstance(minimum_samples, int)
        or minimum_samples < 3
        or not isinstance(interval, (int, float))
        or interval <= 0
        or not isinstance(headroom, (int, float))
        or not 0 < headroom < 1
    ):
        raise ValueError("Sizing sampling or headroom boundary is invalid.")
    for task_name, task in tasks.items():
        if not isinstance(task, dict):
            raise ValueError(f"Task {task_name} is invalid.")
        cpu = task.get("cpuUnits")
        memory = task.get("memoryMiB")
        if (
            not isinstance(cpu, int)
            or not isinstance(memory, int)
            or cpu not in FARGATE_MEMORY_BY_CPU
            or memory not in FARGATE_MEMORY_BY_CPU[cpu]
        ):
            raise ValueError(
                f"Task {task_name} is not a valid Fargate CPU/memory pair."
            )
    concurrent_memory = {task_name: 0 for task_name in tasks}
    expected = {
        "web",
        "api",
        "api-outbox",
        "api-events",
        "api-migration",
        "ml-worker",
    }
    if set(processes) != expected:
        raise ValueError(
            "Sizing configuration does not cover every deployable process."
        )
    for process_name, process in processes.items():
        if not isinstance(process, dict) or process.get("task") not in tasks:
            raise ValueError(f"Process {process_name} has no valid task.")
        candidate = process.get("memoryCandidateMiB")
        if not isinstance(candidate, int) or candidate <= 0:
            raise ValueError(f"Process {process_name} has no memory candidate.")
        if candidate > tasks[process["task"]]["memoryMiB"]:
            raise ValueError(f"Process {process_name} exceeds its task memory.")
        if process.get("concurrent") is True:
            concurrent_memory[process["task"]] += candidate
    for task_name, total in concurrent_memory.items():
        if total > tasks[task_name]["memoryMiB"]:
            raise ValueError(f"Task {task_name} process candidates exceed task memory.")
    return document


def resolve_repository_path(path: Path) -> Path:
    resolved = (
        (REPOSITORY_ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    )
    try:
        resolved.relative_to(REPOSITORY_ROOT)
    except ValueError as error:
        raise ValueError(
            "Measurement paths must stay inside the repository."
        ) from error
    return resolved


@dataclass
class Peak:
    samples: int = 0
    memory_bytes: int = 0
    cpu_percent: float = 0.0
    pids: int = 0


class DockerStatsSampler:
    def __init__(
        self,
        *,
        docker: str,
        container_ids: dict[str, str],
        interval_seconds: float,
    ) -> None:
        self._docker = docker
        self._container_ids = container_ids
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample_until_stopped, daemon=True)
        self.peaks = {service: Peak() for service in container_ids}
        self.error: Exception | None = None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=max(10.0, self._interval_seconds * 3))
        if self._thread.is_alive():
            raise RuntimeError("Container resource sampler did not stop.")
        if self.error is not None:
            raise RuntimeError("Container resource sampling failed.") from self.error

    def _sample_until_stopped(self) -> None:
        try:
            while not self._stop.is_set():
                self._sample_once()
                self._stop.wait(self._interval_seconds)
        except Exception as error:
            self.error = error

    def _sample_once(self) -> None:
        result = subprocess.run(
            [
                self._docker,
                "stats",
                "--no-stream",
                "--format",
                "{{json .}}",
                *self._container_ids.values(),
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        rows = [json.loads(line) for line in result.stdout.splitlines() if line]
        for row in rows:
            identifier = str(row.get("ID", ""))
            service = next(
                (
                    name
                    for name, full_id in self._container_ids.items()
                    if full_id.startswith(identifier)
                ),
                None,
            )
            if service is None:
                raise ValueError("Docker stats returned an unknown container.")
            usage = str(row.get("MemUsage", "")).partition("/")[0]
            peak = self.peaks[service]
            peak.samples += 1
            peak.memory_bytes = max(peak.memory_bytes, parse_memory_bytes(usage))
            peak.cpu_percent = max(peak.cpu_percent, parse_percentage(row["CPUPerc"]))
            peak.pids = max(peak.pids, int(row["PIDs"]))


def compose_container_ids(
    docker: str, project: str, services: list[str]
) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    for service in services:
        result = subprocess.run(
            [docker, "compose", "-p", project, "ps", "-q", service],
            cwd=REPOSITORY_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        values = result.stdout.decode().splitlines()
        if len(values) != 1 or not values[0]:
            raise RuntimeError(f"Expected one running container for {service}.")
        identifiers[service] = values[0]
    return identifiers


def measure_migration(docker: str, project: str) -> float:
    probe = (
        "import json,resource,subprocess;"
        "result=subprocess.run(['alembic','-c','/workspace/apps/api/alembic.ini',"
        "'upgrade','head'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
        "print(json.dumps({'returncode':result.returncode,'maxRssKiB':"
        "resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss}))"
    )
    result = subprocess.run(
        [docker, "compose", "-p", project, "exec", "-T", "api", "python", "-c", probe],
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    payload = json.loads(result.stdout)
    if payload.get("returncode") != 0 or not isinstance(payload.get("maxRssKiB"), int):
        raise RuntimeError("Migration measurement failed.")
    return payload["maxRssKiB"] / 1024


def image_evidence(
    docker: str, container_ids: dict[str, str]
) -> dict[str, dict[str, Any]]:
    inspections = run_json([docker, "inspect", *container_ids.values()])
    by_id = {item["Id"]: item for item in inspections}
    image_ids = sorted({item["Image"] for item in inspections})
    image_inspections = run_json([docker, "image", "inspect", *image_ids])
    image_sizes = {item["Id"]: item["Size"] for item in image_inspections}
    evidence: dict[str, dict[str, Any]] = {}
    for service, container_id in container_ids.items():
        inspection = by_id[container_id]
        image_id = inspection["Image"]
        evidence[service] = {
            "configuredImage": inspection["Config"]["Image"],
            "imageId": image_id,
            "imageSizeBytes": image_sizes[image_id],
        }
    return evidence


def source_identity() -> tuple[str, str]:
    checkout = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            stdout=subprocess.PIPE,
        )
        .stdout.decode()
        .strip()
    )
    selected = os.environ.get("PORTFOLIO_VERIFICATION_HEAD_SHA", checkout)
    if FULL_SHA.fullmatch(selected) is None:
        raise ValueError("Verification source SHA is not an exact commit.")
    subprocess.run(
        ["git", "cat-file", "-e", f"{selected}^{{commit}}"],
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["git", "diff", "--quiet", selected, checkout, "--"],
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return selected, checkout


def write_summary(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path is None:
        return
    lines = [
        "## Measured container sizing",
        "",
        f"- Source: `{evidence['sourceSha']}`",
        f"- Samples: `{evidence['sampling']['sampleCount']}` per long-running process",
        f"- Workload: {evidence['workload']}",
        "",
        "| Process | Peak memory MiB | Candidate MiB | Peak CPU % | Image size MiB |",
        "|---|---:|---:|---:|---:|",
    ]
    for process, observation in evidence["processes"].items():
        lines.append(
            f"| {process} | {observation['peakMemoryMiB']} | "
            f"{observation['memoryCandidateMiB']} | "
            f"{observation.get('peakCpuPercent', 'n/a')} | "
            f"{observation['imageSizeMiB']} |"
        )
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compose-project", required=True)
    parser.add_argument("workload", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configuration_path = resolve_repository_path(args.configuration)
    output_path = resolve_repository_path(args.output)
    workload = args.workload[1:] if args.workload[:1] == ["--"] else args.workload
    if not workload:
        raise ValueError("A representative workload command is required.")
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("Docker is required for container measurement.")
    configuration = load_configuration(configuration_path)
    process_config = configuration["processes"]
    long_running = [process for process in process_config if process != "api-migration"]
    container_ids = compose_container_ids(docker, args.compose_project, long_running)
    images = image_evidence(docker, container_ids)
    source_sha, checkout_sha = source_identity()
    migration_peak = measure_migration(docker, args.compose_project)
    measurement = configuration["measurement"]
    sampler = DockerStatsSampler(
        docker=docker,
        container_ids=container_ids,
        interval_seconds=float(measurement["sampleIntervalSeconds"]),
    )
    started_at = utc_now()
    sampler.start()
    workload_result = subprocess.run(workload, cwd=REPOSITORY_ROOT, check=False)
    sampler.stop()
    completed_at = utc_now()
    if workload_result.returncode != 0:
        return workload_result.returncode
    minimum_samples = measurement["minimumSamples"]
    if any(peak.samples < minimum_samples for peak in sampler.peaks.values()):
        raise RuntimeError(
            "The workload completed before the minimum sampling boundary."
        )

    observations: dict[str, dict[str, Any]] = {}
    minimum_headroom = float(measurement["minimumHeadroomFraction"])
    for process, peak in sampler.peaks.items():
        candidate = process_config[process]["memoryCandidateMiB"]
        peak_mib = peak.memory_bytes / 1024**2
        if peak_mib > candidate * (1 - minimum_headroom):
            raise RuntimeError(
                f"Measured {process} memory exceeds its headroom boundary."
            )
        observations[process] = {
            **images[process],
            "imageSizeMiB": round(images[process]["imageSizeBytes"] / 1024**2, 2),
            "memoryCandidateMiB": candidate,
            "peakMemoryMiB": round(peak_mib, 2),
            "peakCpuPercent": round(peak.cpu_percent, 2),
            "peakPids": peak.pids,
            "samples": peak.samples,
            "task": process_config[process]["task"],
        }
    migration_candidate = process_config["api-migration"]["memoryCandidateMiB"]
    if migration_peak > migration_candidate * (1 - minimum_headroom):
        raise RuntimeError(
            "Measured api-migration memory exceeds its headroom boundary."
        )
    observations["api-migration"] = {
        **images["api"],
        "imageSizeMiB": round(images["api"]["imageSizeBytes"] / 1024**2, 2),
        "memoryCandidateMiB": migration_candidate,
        "peakMemoryMiB": round(migration_peak, 2),
        "peakCpuPercent": "not sampled for bounded one-shot process",
        "peakPids": "not sampled for bounded one-shot process",
        "samples": 1,
        "task": "api-area",
    }
    config_bytes = configuration_path.read_bytes()
    evidence = {
        "schemaVersion": 1,
        "sourceSha": source_sha,
        "checkoutSha": checkout_sha,
        "configuration": configuration_path.relative_to(REPOSITORY_ROOT).as_posix(),
        "configurationSha256": hashlib.sha256(config_bytes).hexdigest(),
        "workload": measurement["workload"],
        "workloadCommand": [Path(workload[0]).name, *workload[1:]],
        "sampling": {
            "startedAt": started_at,
            "completedAt": completed_at,
            "intervalSeconds": measurement["sampleIntervalSeconds"],
            "sampleCount": min(peak.samples for peak in sampler.peaks.values()),
            "minimumHeadroomFraction": minimum_headroom,
        },
        "uncertainty": measurement["uncertainty"],
        "tasks": configuration["tasks"],
        "processes": dict(sorted(observations.items())),
    }
    write_summary(output_path, evidence)
    print(f"Container sizing evidence written to {output_path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
