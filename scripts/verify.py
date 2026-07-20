from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PROJECT_NAME = "reactorfront-portfolio"
ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "verification"


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
            "Lint Web source and tests",
            [pnpm, "--filter", "@reactorfront/web", "lint"],
        ),
        (
            "Check Web formatting",
            [pnpm, "--filter", "@reactorfront/web", "format:check"],
        ),
        (
            "Type-check Web source",
            [pnpm, "--filter", "@reactorfront/web", "typecheck"],
        ),
        (
            "Run Web branch-aware tests",
            [pnpm, "--filter", "@reactorfront/web", "test:coverage"],
        ),
        (
            "Build the production Web application",
            [pnpm, "--filter", "@reactorfront/web", "build"],
        ),
        (
            "Audit the pinned Web production dependency set",
            [
                pnpm,
                "audit",
                "--prod",
                "--audit-level",
                "moderate",
            ],
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
                "scripts/verify_outbox_runtime.py",
                "scripts/verify_result_consumer_runtime.py",
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
                "scripts/verify_outbox_runtime.py",
                "scripts/verify_result_consumer_runtime.py",
                "scripts/check_docs.py",
            ],
        ),
        (
            "Type-check API source",
            [
                uv,
                "run",
                "--project",
                "apps/api",
                "mypy",
                "--config-file",
                "apps/api/pyproject.toml",
                "apps/api/src",
            ],
        ),
        (
            "Audit the installed pinned API dependency set",
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
        (
            "Lint ML source, tests, and verification helpers",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "ruff",
                "check",
                "apps/ml/src",
                "apps/ml/tests",
                "scripts/pdf_fixture.py",
                "scripts/check_ml_compose_boundary.py",
                "scripts/verify_ml_model.py",
                "scripts/verify_ml_runtime.py",
            ],
        ),
        (
            "Check ML formatting",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "ruff",
                "format",
                "--check",
                "apps/ml/src",
                "apps/ml/tests",
                "scripts/pdf_fixture.py",
                "scripts/check_ml_compose_boundary.py",
                "scripts/verify_ml_model.py",
                "scripts/verify_ml_runtime.py",
            ],
        ),
        (
            "Type-check ML source",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "mypy",
                "--config-file",
                "apps/ml/pyproject.toml",
                "apps/ml/src",
            ],
        ),
        (
            "Audit the installed pinned ML dependency set",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "pip-audit",
                "--local",
                "--skip-editable",
                "--progress-spinner=off",
            ],
        ),
        (
            "Audit the normalized PyTorch CPU release identity",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "pip-audit",
                "--requirement",
                "apps/ml/audit-requirements.txt",
                "--disable-pip",
                "--progress-spinner=off",
            ],
        ),
        (
            "Prove deterministic ML model generation",
            [
                uv,
                "run",
                "--project",
                "apps/ml",
                "python",
                "scripts/verify_ml_model.py",
            ],
        ),
        (
            "Validate deployable Compose boundaries",
            [sys.executable, "scripts/check_ml_compose_boundary.py"],
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
            "--cov-report=xml:artifacts/verification/api-coverage.xml",
            "--cov-fail-under=90",
            "--junitxml=artifacts/verification/api-pytest.xml",
        ]
    )
    return command


def pytest_ml_command(uv: str) -> list[str]:
    return [
        uv,
        "run",
        "--project",
        "apps/ml",
        "pytest",
        "apps/ml/tests",
        "--cov=reactorfront_ml",
        "--cov-branch",
        "--cov-report=term-missing",
        "--cov-report=xml:artifacts/verification/ml-coverage.xml",
        "--cov-fail-under=90",
        "--junitxml=artifacts/verification/ml-pytest.xml",
    ]


def run_runtime_checks(*, uv: str, docker: str) -> None:
    run("Run ML unit tests", pytest_ml_command(uv))
    run(
        "Build and start isolated PostgreSQL, MinIO, and RabbitMQ",
        compose_command(
            docker,
            "up",
            "--detach",
            "--build",
            "--wait",
            "postgres",
            "minio",
            "rabbitmq",
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
        "Build and start the source-owned Web container",
        compose_command(docker, "up", "--detach", "--build", "--wait", "web"),
    )
    run(
        "Prove the Web container is healthy and non-root",
        compose_command(
            docker,
            "exec",
            "-T",
            "web",
            "node",
            "-e",
            "if (process.getuid?.() === 0) process.exit(1); "
            "fetch('http://127.0.0.1:3000/health')"
            ".then((response) => { if (!response.ok) process.exit(1); })"
            ".catch(() => process.exit(1));",
        ),
    )
    run(
        "Run API unit and real-service integration tests",
        pytest_command(uv, include_integration=True),
    )
    run(
        "Prove outbox and RabbitMQ restart recovery",
        [
            uv,
            "run",
            "--project",
            "apps/api",
            "python",
            "scripts/verify_outbox_runtime.py",
        ],
    )
    run(
        "Prove the real ML worker and result-event boundary",
        [
            uv,
            "run",
            "--project",
            "apps/ml",
            "python",
            "scripts/verify_ml_runtime.py",
        ],
    )
    run(
        "Prove API-owned result-event consumption and terminal persistence",
        [
            uv,
            "run",
            "--project",
            "apps/api",
            "python",
            "scripts/verify_result_consumer_runtime.py",
        ],
    )


def capture_runtime_diagnostic(
    *,
    label: str,
    command: list[str],
    filename: str,
) -> None:
    print(f"\n==> {label}", flush=True)
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = result.stdout or b""
    sys.stdout.buffer.write(output)
    sys.stdout.flush()
    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIRECTORY / filename).write_bytes(output)


def show_runtime_diagnostics(docker: str) -> None:
    capture_runtime_diagnostic(
        label="Show isolated Compose state",
        command=compose_command(docker, "ps", "--all"),
        filename="compose-ps.txt",
    )
    capture_runtime_diagnostic(
        label="Show isolated service logs",
        command=compose_command(
            docker,
            "logs",
            "--no-color",
            "--timestamps",
            "--tail",
            "500",
        ),
        filename="compose-logs.txt",
    )
    capture_runtime_diagnostic(
        label="Show ML worker dependency readiness",
        command=compose_command(
            docker,
            "exec",
            "-T",
            "ml-worker",
            "python",
            "-m",
            "reactorfront_ml.health",
            "--check",
        ),
        filename="ml-readiness.txt",
    )
    capture_runtime_diagnostic(
        label="Show API event-consumer dependency readiness",
        command=compose_command(
            docker,
            "exec",
            "-T",
            "api-events",
            "python",
            "-m",
            "reactorfront_api.events_main",
            "--check",
        ),
        filename="api-events-readiness.txt",
    )
    capture_runtime_diagnostic(
        label="Show Web process health",
        command=compose_command(
            docker,
            "exec",
            "-T",
            "web",
            "node",
            "-e",
            "fetch('http://127.0.0.1:3000/health')"
            ".then(async (response) => { console.log(await response.text()); "
            "if (!response.ok) process.exit(1); })"
            ".catch(() => process.exit(1));",
        ),
        filename="web-health.txt",
    )


def cleanup_runtime(docker: str) -> None:
    remove_volumes = os.environ.get("GITHUB_ACTIONS") == "true"
    scope = f"Compose project {COMPOSE_PROJECT_NAME}"
    if remove_volumes:
        scope += " including its three project-scoped data volumes"
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
    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
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
            run("Run ML unit tests", pytest_ml_command(uv))
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
