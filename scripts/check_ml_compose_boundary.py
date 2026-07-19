from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PROJECT_NAME = "reactorfront-portfolio"
CPU_INDEX = "https://download.pytorch.org/whl/cpu"


def main() -> int:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            COMPOSE_PROJECT_NAME,
            "config",
            "--format",
            "json",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    config = json.loads(result.stdout)
    services = config["services"]
    worker = services["ml-worker"]
    environment = worker.get("environment", {})
    forbidden = [
        name
        for name in environment
        if "DATABASE" in name.upper() or "POSTGRES" in name.upper()
    ]
    if forbidden:
        raise RuntimeError(f"ML worker has forbidden database settings: {forbidden}")
    if worker.get("ports"):
        raise RuntimeError("ML worker must not publish a host port")
    if "web" in services:
        raise RuntimeError(
            "Current product boundary unexpectedly includes the Web service"
        )
    events = services.get("api-events")
    if events is None:
        raise RuntimeError("API-owned result-event consumer service is missing")
    events_environment = events.get("environment", {})
    if not any("DATABASE" in name.upper() for name in events_environment):
        raise RuntimeError(
            "API result consumer is missing its API-owned database setting"
        )
    forbidden_event_settings = sorted(
        name
        for name in events_environment
        if name.startswith("PORTFOLIO_ML_") or "S3" in name.upper()
    )
    if forbidden_event_settings:
        raise RuntimeError(
            "API result consumer has unrelated ML/object-storage settings: "
            f"{forbidden_event_settings}"
        )
    if events.get("ports"):
        raise RuntimeError("API result consumer must not publish a host port")
    command = events.get("command", [])
    if "reactorfront_api.events_main" not in command:
        raise RuntimeError("API result consumer does not run the reviewed process role")

    api_source = REPOSITORY_ROOT / "apps" / "api" / "src"
    private_ml_imports = sorted(
        str(path.relative_to(REPOSITORY_ROOT))
        for path in api_source.rglob("*.py")
        if any(
            line.lstrip().startswith(("from reactorfront_ml", "import reactorfront_ml"))
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    )
    if private_ml_imports:
        raise RuntimeError(
            f"API source imports private ML implementation: {private_ml_imports}"
        )

    dockerfile = (REPOSITORY_ROOT / "infra" / "docker" / "ml" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    missing_worker_flags = [
        flag
        for flag in ("--without-gossip", "--without-mingle")
        if flag not in dockerfile
    ]
    if missing_worker_flags:
        raise RuntimeError(
            "ML worker enables unused Celery cluster topology: "
            f"missing {missing_worker_flags}"
        )

    lock = tomllib.loads(
        (REPOSITORY_ROOT / "apps" / "ml" / "uv.lock").read_text(encoding="utf-8")
    )
    packages = lock["package"]
    forbidden_packages = sorted(
        package["name"]
        for package in packages
        if package["name"].startswith(("cuda-", "nvidia-"))
        or package["name"] == "triton"
    )
    if forbidden_packages:
        raise RuntimeError(f"ML CPU lock contains GPU packages: {forbidden_packages}")
    torch_sources = {
        package["source"].get("registry")
        for package in packages
        if package["name"] == "torch"
    }
    if torch_sources != {CPU_INDEX}:
        raise RuntimeError(
            f"PyTorch is not pinned only to the CPU index: {torch_sources}"
        )
    pyproject = tomllib.loads(
        (REPOSITORY_ROOT / "apps" / "ml" / "pyproject.toml").read_text(encoding="utf-8")
    )
    torch_requirement = next(
        dependency
        for dependency in pyproject["project"]["dependencies"]
        if dependency.startswith("torch==")
    )
    audited_entries = {
        line.strip()
        for line in (REPOSITORY_ROOT / "apps" / "ml" / "audit-requirements.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.startswith("#")
    }
    cpu_torch = next(
        package
        for package in packages
        if package["name"] == "torch" and package["version"].endswith("+cpu")
    )
    linux_wheel = next(
        wheel
        for wheel in cpu_torch["wheels"]
        if "manylinux_2_28_x86_64" in wheel["url"]
    )
    expected_audit_entry = f"{torch_requirement} --hash={linux_wheel['hash']}"
    if audited_entries != {expected_audit_entry}:
        raise RuntimeError("Normalized PyTorch audit identity has drifted")
    print(
        "ML boundary passed: CPU-only lock plus no database settings, host port, "
        "or unused Celery cluster topology; API-owned result consumption remains isolated."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
