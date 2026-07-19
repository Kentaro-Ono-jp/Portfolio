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
    if "api-events" in services or "web" in services:
        raise RuntimeError("Focused ML increment includes an out-of-scope service")

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
        "API result consumer, or Web service."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
