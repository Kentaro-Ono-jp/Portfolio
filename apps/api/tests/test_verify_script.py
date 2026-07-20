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
        lambda: argparse.Namespace(
            static_only=False,
            groups=None,
            plan=False,
            base=None,
            staged=False,
            full=False,
            github_output=None,
            summary=None,
        ),
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
    assert "scripts/verify_outbox_runtime.py" in checks["Lint API source and tests"]
    assert checks["Type-check ML source"] == [
        "uv",
        "run",
        "--project",
        "apps/ml",
        "mypy",
        "--config-file",
        "apps/ml/pyproject.toml",
        "apps/ml/src",
    ]
    assert (
        "scripts/verify_ml_runtime.py" in checks["Lint ML source, tests, and verification helpers"]
    )


def test_pytest_command_writes_machine_readable_evidence(verifier: ModuleType) -> None:
    command = verifier.pytest_command("uv", include_integration=True)

    assert "--cov-report=xml:artifacts/verification/api-coverage.xml" in command
    assert "--junitxml=artifacts/verification/api-pytest.xml" in command
    assert "-m" not in command


def test_ml_pytest_command_writes_separate_branch_coverage_evidence(
    verifier: ModuleType,
) -> None:
    command = verifier.pytest_ml_command("uv")

    assert "--cov-branch" in command
    assert "--cov-report=xml:artifacts/verification/ml-coverage.xml" in command
    assert "--junitxml=artifacts/verification/ml-pytest.xml" in command


def test_web_test_change_selects_only_web_static_group(verifier: ModuleType) -> None:
    plan = verifier.plan_for_paths(
        ["apps/web/src/lib/polling.test.ts"],
        base="baseline",
    )

    assert plan.groups == {"web-static"}
    assert plan.base == "baseline"


def test_api_source_change_selects_static_runtime_and_compose(
    verifier: ModuleType,
) -> None:
    plan = verifier.plan_for_paths(
        ["apps/api/src/reactorfront_api/service.py"],
    )

    assert plan.groups == {"compose", "api-static", "api-runtime"}


@pytest.mark.parametrize(
    "path",
    [
        "packages/contracts/events/job-requested.schema.json",
        "scripts/verify.py",
        ".github/workflows/verify.yml",
        "unmapped-config.toml",
    ],
)
def test_cross_cutting_or_unknown_change_fails_closed_to_every_group(
    verifier: ModuleType,
    path: str,
) -> None:
    plan = verifier.plan_for_paths([path])

    assert plan.groups == verifier.ALL_GROUPS
    assert "full verification" in plan.reason


def test_documentation_change_selects_only_documentation(verifier: ModuleType) -> None:
    plan = verifier.plan_for_paths(["docs/ai/README.md"])

    assert plan.groups == {"docs"}


def test_plan_reports_dynamic_test_file_selection(verifier: ModuleType) -> None:
    inventory = verifier.test_file_inventory()
    plan = verifier.VerificationPlan(
        groups=frozenset({"web-static"}),
        changed_files=("apps/web/src/lib/polling.ts",),
        reason="test",
    )

    assert len(inventory) == 34
    assert len(verifier.selected_test_files(plan.groups)) == 9
    assert "Verification groups: 1/9 selected" in verifier.plan_lines(plan)
    assert "Test files: 9/34 selected" in verifier.plan_lines(plan)


def test_plan_output_drives_conditional_dependency_setup(
    verifier: ModuleType,
    tmp_path: Path,
) -> None:
    output = tmp_path / "github-output.txt"
    plan = verifier.plan_for_paths(["apps/ml/tests/test_model.py"])

    verifier.write_plan_outputs(plan, output)

    values = dict(
        line.split("=", maxsplit=1) for line in output.read_text(encoding="utf-8").splitlines()
    )
    assert values["groups"] == "ml-static"
    assert values["needs_node"] == "false"
    assert values["needs_api"] == "false"
    assert values["needs_ml"] == "true"
    assert values["needs_docker"] == "false"


def test_docs_group_does_not_require_unrelated_toolchains(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels: list[str] = []
    monkeypatch.setattr(
        verifier,
        "parse_args",
        lambda: argparse.Namespace(
            static_only=False,
            groups="docs",
            plan=False,
            base=None,
            staged=False,
            full=False,
            github_output=None,
            summary=None,
        ),
    )
    monkeypatch.setattr(
        verifier,
        "require_command",
        lambda command: pytest.fail(f"unexpected tool requirement: {command}"),
    )
    monkeypatch.setattr(
        verifier,
        "run",
        lambda label, _command: labels.append(label),
    )

    assert verifier.main() == 0
    assert labels == ["Validate documentation links"]


def test_unknown_explicit_group_returns_a_clean_failure(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        verifier,
        "parse_args",
        lambda: argparse.Namespace(
            static_only=False,
            groups="unknown",
            plan=False,
            base=None,
            staged=False,
            full=False,
            github_output=None,
            summary=None,
        ),
    )

    assert verifier.main() == 1
    assert "Unknown verification groups: unknown" in capsys.readouterr().err


def test_runtime_groups_skip_unselected_service_proofs(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels: list[str] = []
    monkeypatch.setattr(
        verifier,
        "run",
        lambda label, _command: labels.append(label),
    )

    verifier.run_runtime_checks(
        groups=frozenset({"web-runtime"}),
        uv="uv",
        docker="docker",
    )

    assert "Prove the Web container is healthy and non-root" in labels
    assert "Run API unit and real-service integration tests" not in labels
    assert "Prove the real ML worker and result-event boundary" not in labels


def test_runtime_diagnostics_are_persisted(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(verifier, "ARTIFACT_DIRECTORY", tmp_path)
    monkeypatch.setattr(
        verifier.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["docker"],
            returncode=1,
            stdout=b"sanitized diagnostics\n",
        ),
    )

    verifier.capture_runtime_diagnostic(
        label="Capture diagnostics",
        command=["docker", "compose", "ps"],
        filename="compose-ps.txt",
    )

    assert (tmp_path / "compose-ps.txt").read_bytes() == b"sanitized diagnostics\n"


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
