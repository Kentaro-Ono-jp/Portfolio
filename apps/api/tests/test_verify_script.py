from __future__ import annotations

import argparse
import importlib.util
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def verifier() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts" / "verify.py"
    specification = importlib.util.spec_from_file_location("portfolio_verify", path)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def configure_runtime_verification(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    *,
    runtime_check: Callable[..., None],
    cleanup: Callable[[str], None],
) -> None:
    monkeypatch.setattr(
        verifier,
        "parse_args",
        lambda: argparse.Namespace(static_only=False),
    )
    monkeypatch.setattr(verifier, "require_command", lambda command: command)
    monkeypatch.setattr(verifier, "static_checks", lambda **_commands: [])
    monkeypatch.setattr(verifier, "run_runtime_checks", runtime_check)
    monkeypatch.setattr(verifier, "cleanup_runtime", cleanup)
    monkeypatch.setattr(verifier, "show_runtime_diagnostics", lambda _docker: None)


def test_static_checks_load_the_api_mypy_configuration(verifier: ModuleType) -> None:
    checks = dict(verifier.static_checks(pnpm="pnpm", uv="uv", docker="docker"))

    assert checks["Type-check API source"] == [
        "uv",
        "run",
        "--project",
        "apps/api",
        "mypy",
        "--config-file",
        "apps/api/pyproject.toml",
        "apps/api/src",
    ]


def test_verifier_returns_success_only_when_checks_and_cleanup_succeed(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_runtime_verification(
        verifier,
        monkeypatch,
        runtime_check=lambda **_commands: None,
        cleanup=lambda _docker: None,
    )

    assert verifier.main() == 0


def test_verifier_preserves_main_failure_and_still_runs_cleanup(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_called = False

    def fail_runtime(**_commands: str) -> None:
        raise RuntimeError("verification fault")

    def cleanup(_docker: str) -> None:
        nonlocal cleanup_called
        cleanup_called = True

    configure_runtime_verification(
        verifier,
        monkeypatch,
        runtime_check=fail_runtime,
        cleanup=cleanup,
    )

    assert verifier.main() == 1
    assert cleanup_called


def test_verifier_returns_failure_when_cleanup_fails_after_success(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_cleanup(_docker: str) -> None:
        raise subprocess.CalledProcessError(1, ["docker", "compose", "down"])

    configure_runtime_verification(
        verifier,
        monkeypatch,
        runtime_check=lambda **_commands: None,
        cleanup=fail_cleanup,
    )

    assert verifier.main() == 1


def test_verifier_reports_main_and_cleanup_failures_together(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_runtime(**_commands: str) -> None:
        raise RuntimeError("verification fault")

    def fail_cleanup(_docker: str) -> None:
        raise subprocess.CalledProcessError(1, ["docker", "compose", "down"])

    configure_runtime_verification(
        verifier,
        monkeypatch,
        runtime_check=fail_runtime,
        cleanup=fail_cleanup,
    )

    assert verifier.main() == 1
    error_output = capsys.readouterr().err
    assert "Verification failed" in error_output
    assert "Runtime cleanup failed" in error_output
