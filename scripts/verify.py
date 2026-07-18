from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PROJECT_NAME = "reactorfront-portfolio"


def require_command(command: str) -> str:
    resolved = shutil.which(command)
    if resolved is None:
        raise RuntimeError(f"Required command is not available: {command}")
    return resolved


def run(label: str, command: list[str]) -> None:
    print(f"\n==> {label}", flush=True)
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)


def main() -> int:
    pnpm = require_command("pnpm")
    docker = require_command("docker")

    checks = [
        ("Validate canonical contracts", [pnpm, "contracts:check"]),
        (
            "Validate documentation links",
            [sys.executable, "scripts/check_docs.py"],
        ),
        (
            "Validate the isolated Compose definition",
            [
                docker,
                "compose",
                "-p",
                COMPOSE_PROJECT_NAME,
                "config",
                "--quiet",
            ],
        ),
    ]

    try:
        for label, command in checks:
            run(label, command)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"\nVerification failed: {error}", file=sys.stderr)
        return 1

    print("\nVerification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
