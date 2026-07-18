from __future__ import annotations

import argparse
import os
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


def run(
    label: str, command: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[bytes]:
    print(f"\n==> {label}", flush=True)
    return subprocess.run(command, cwd=REPOSITORY_ROOT, check=check)


def compose_command(docker: str, *arguments: str) -> list[str]:
    return [docker, "compose", "-p", COMPOSE_PROJECT_NAME, *arguments]


def static_checks(*, pnpm: str, uv: str, docker: str) -> list[tuple[str, list[str]]]:
    return [
        ("Validate canonical contracts", [pnpm, "contracts:check"]),
        ("Validate documentation links", [sys.executable, "scripts/check_docs.py"]),
        (
            "Validate the isolated Compose definition",
            compose_command(docker, "config", "--quiet"),
        ),
        (
            "Lint API source and tests",
            [
                uv,
                "run",
                "--project",
                "apps/api",
                "ruff",
                "check",
                "apps/api/src",
                "apps/api/alembic",
                "apps/api/tests",
                "scripts/verify.py",
                "scripts/prepare_integration.py",
                "scripts/check_docs.py",
            ],
        ),
        (
            "Check API formatting",
            [
                uv,
                "run",
                "--project",
                "apps/api",
                "ruff",
                "format",
                "--check",
                "apps/api/src",
                "apps/api/alembic",
                "apps/api/tests",
                "scripts/verify.py",
                "scripts/prepare_integration.py",
                "scripts/check_docs.py",
            ],
        ),
        (
            "Type-check API source",
            [uv, "run", "--project", "apps/api", "mypy", "apps/api/src"],
        ),
        (
            "Audit the installed pinned Python dependency set",
            [
                uv,
                "run",
                "--project",
                "apps/api",
                "pip-audit",
                "--local",
                "--skip-editable",
                "--progress-spinner=off",
            ],
        ),
    ]


def pytest_command(uv: str, *, include_integration: bool) -> list[str]:
    command = [
        uv,
        "run",
        "--project",
        "apps/api",
        "pytest",
        "apps/api/tests",
    ]
    if not include_integration:
        command.extend(["-m", "not integration"])
    command.extend(
        [
            "--cov=reactorfront_api",
            "--cov-branch",
            "--cov-report=term-missing",
            "--cov-fail-under=90",
        ]
    )
    return command


def run_runtime_checks(*, uv: str, docker: str) -> None:
    run(
        "Build and start isolated PostgreSQL and MinIO",
        compose_command(
            docker, "up", "--detach", "--build", "--wait", "postgres", "minio"
        ),
    )
    run(
        "Create the deterministic integration bucket",
        [
            uv,
            "run",
            "--project",
            "apps/api",
            "python",
            "scripts/prepare_integration.py",
        ],
    )
    run(
        "Apply API database migrations",
        [
            uv,
            "run",
            "--project",
            "apps/api",
            "alembic",
            "-c",
            "apps/api/alembic.ini",
            "upgrade",
            "head",
        ],
    )
    run(
        "Check migration metadata drift",
        [
            uv,
            "run",
            "--project",
            "apps/api",
            "alembic",
            "-c",
            "apps/api/alembic.ini",
            "check",
        ],
    )
    run(
        "Build and start the migrated API container",
        compose_command(docker, "up", "--detach", "--build", "--wait", "api"),
    )
    run(
        "Run API unit and real-service integration tests",
        pytest_command(uv, include_integration=True),
    )


def show_runtime_diagnostics(docker: str) -> None:
    run("Show isolated Compose state", compose_command(docker, "ps"), check=False)
    run(
        "Show isolated service logs",
        compose_command(docker, "logs", "--no-color", "--tail", "200"),
        check=False,
    )


def cleanup_runtime(docker: str) -> None:
    remove_volumes = os.environ.get("GITHUB_ACTIONS") == "true"
    scope = f"Compose project {COMPOSE_PROJECT_NAME}"
    if remove_volumes:
        scope += " including its two project-scoped data volumes"
    print(f"\n==> Cleanup target: {scope}", flush=True)
    arguments = ["down", "--remove-orphans"]
    if remove_volumes:
        arguments.append("--volumes")
    run("Stop the isolated runtime", compose_command(docker, *arguments))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run canonical repository verification."
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Skip container startup and real-service integration tests.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime_started = False
    verification_error: RuntimeError | subprocess.CalledProcessError | None = None
    cleanup_error: subprocess.CalledProcessError | None = None
    try:
        pnpm = require_command("pnpm")
        uv = require_command("uv")
        docker = require_command("docker")

        for label, command in static_checks(pnpm=pnpm, uv=uv, docker=docker):
            run(label, command)

        if args.static_only:
            run("Run API unit tests", pytest_command(uv, include_integration=False))
        else:
            runtime_started = True
            run_runtime_checks(uv=uv, docker=docker)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"\nVerification failed: {error}", file=sys.stderr)
        verification_error = error
        if runtime_started:
            show_runtime_diagnostics(docker)
    finally:
        if runtime_started:
            try:
                cleanup_runtime(docker)
            except subprocess.CalledProcessError as error:
                cleanup_error = error
                print(f"\nRuntime cleanup failed: {error}", file=sys.stderr)

    if verification_error is not None or cleanup_error is not None:
        return 1

    print("\nVerification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
