from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def verifier_args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "static_only": False,
        "groups": None,
        "plan": False,
        "base": None,
        "staged": False,
        "full": False,
        "carry_all": False,
        "baseline_proven": False,
        "baseline_skipped_groups": None,
        "carried_groups": None,
        "skipped_groups": None,
        "github_output": None,
        "summary": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


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
        verifier_args,
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
    assert plan.carried_groups == set()
    assert plan.skipped_groups == verifier.ALL_GROUPS - {"docs"}


def test_successful_baseline_marks_unaffected_groups_as_carried(
    verifier: ModuleType,
) -> None:
    plan = verifier.plan_for_paths(
        ["docs/ai/README.md"],
        base="successful-head",
        baseline_proven=True,
    )

    assert plan.groups == {"docs"}
    assert plan.carried_groups == verifier.ALL_GROUPS - {"docs"}
    assert plan.skipped_groups == set()
    assert any(
        line.startswith("Carried from successful baseline: contracts")
        for line in verifier.plan_lines(plan)
    )
    assert "Skipped without evidence: none" in verifier.plan_lines(plan)


def test_identical_tree_can_carry_every_group(verifier: ModuleType) -> None:
    args = verifier_args(plan=True, carry_all=True, baseline_proven=True)

    plan = verifier.resolve_selection(args)

    assert plan.groups == set()
    assert plan.carried_groups == verifier.ALL_GROUPS
    assert plan.skipped_groups == set()


def test_affected_groups_cannot_be_relabelled_as_carried(
    verifier: ModuleType,
) -> None:
    args = verifier_args(
        groups="contracts,compose",
        carried_groups="compose",
    )

    with pytest.raises(RuntimeError, match="Executed and carried groups overlap: compose"):
        verifier.resolve_selection(args)


def test_planning_rejects_explicit_carry_override(verifier: ModuleType) -> None:
    args = verifier_args(
        plan=True,
        full=True,
        baseline_proven=True,
        carried_groups="compose",
    )

    with pytest.raises(RuntimeError, match="only valid with --groups"):
        verifier.resolve_selection(args)


def test_selected_docker_groups_can_be_reported_as_skipped(
    verifier: ModuleType,
) -> None:
    plan = verifier.plan_for_paths(["scripts/verify.py"], baseline_proven=True)

    plan = verifier.move_groups_to_skipped(plan, verifier.DOCKER_GROUPS)

    assert plan.groups == verifier.STATIC_GROUPS - {"compose"}
    assert plan.carried_groups == set()
    assert plan.skipped_groups == verifier.DOCKER_GROUPS


def test_docs_follow_up_preserves_groups_skipped_by_successful_baseline(
    verifier: ModuleType,
) -> None:
    initial = verifier.plan_for_paths(["scripts/verify.py"], baseline_proven=True)
    initial = verifier.move_groups_to_skipped(initial, verifier.DOCKER_GROUPS)

    follow_up = verifier.plan_for_paths(
        ["docs/ai/README.md"],
        baseline_proven=True,
        baseline_skipped_groups=initial.skipped_groups,
    )
    follow_up = verifier.move_groups_to_skipped(
        follow_up,
        initial.skipped_groups,
    )

    assert follow_up.groups == {"docs"}
    assert follow_up.carried_groups == {
        "contracts",
        "web-static",
        "api-static",
        "ml-static",
    }
    assert follow_up.skipped_groups == verifier.DOCKER_GROUPS


def test_current_skip_cannot_replace_carried_baseline_evidence(
    verifier: ModuleType,
) -> None:
    plan = verifier.plan_for_paths(
        ["docs/ai/README.md"],
        baseline_proven=True,
    )

    with pytest.raises(RuntimeError, match="Cannot relabel carried baseline evidence"):
        verifier.move_groups_to_skipped(plan, frozenset({"compose"}))


def test_cross_boundary_rename_selects_old_and_new_path_groups(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def completed(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert "--name-status" in command
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=(b"R100\0apps/api/src/reactorfront_api/legacy.py\0docs/legacy.md\0"),
        )

    monkeypatch.setattr(verifier.subprocess, "run", completed)

    plan = verifier.plan_from_git(base="baseline")

    assert plan.changed_files == (
        "apps/api/src/reactorfront_api/legacy.py",
        "docs/legacy.md",
    )
    assert plan.groups == {"docs", "compose", "api-static", "api-runtime"}


def test_baseline_skips_require_a_diff_plan(verifier: ModuleType) -> None:
    with pytest.raises(RuntimeError, match="only valid with --base or --staged"):
        verifier.resolve_selection(
            verifier_args(
                groups="docs",
                baseline_proven=True,
                baseline_skipped_groups="compose",
            )
        )


def test_web_health_change_selects_web_runtime(verifier: ModuleType) -> None:
    plan = verifier.plan_for_paths(["apps/web/src/app/health/route.ts"])

    assert plan.groups == {"compose", "web-static", "web-runtime"}


def test_plan_reports_dynamic_test_file_selection(verifier: ModuleType) -> None:
    inventory = verifier.test_file_inventory()
    plan = verifier.VerificationPlan(
        groups=frozenset({"web-static"}),
        changed_files=("apps/web/src/lib/polling.ts",),
        reason="test",
    )

    assert len(inventory) == 35
    assert len(verifier.selected_test_files(plan.groups)) == 9
    assert "Verification groups: 1/9 selected" in verifier.plan_lines(plan)
    assert "Test files: 9/35 selected" in verifier.plan_lines(plan)


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
    assert values["needs_e2e"] == "false"
    assert values["executed_groups"] == "ml-static"
    assert values["carried_groups"] == ""
    assert values["skipped_groups"] != ""


def test_skipped_docker_groups_do_not_request_docker_setup(
    verifier: ModuleType,
    tmp_path: Path,
) -> None:
    output = tmp_path / "github-output.txt"
    plan = verifier.plan_for_paths(
        ["scripts/verify.py"],
        baseline_proven=True,
    )
    plan = verifier.move_groups_to_skipped(plan, verifier.DOCKER_GROUPS)

    verifier.write_plan_outputs(plan, output)

    values = dict(
        line.split("=", maxsplit=1) for line in output.read_text(encoding="utf-8").splitlines()
    )
    assert values["groups"] == "contracts,docs,web-static,api-static,ml-static"
    assert values["carried_groups"] == ""
    assert values["skipped_groups"] == "compose,web-runtime,api-runtime,ml-runtime"
    assert values["docker_groups"] == ""
    assert values["needs_docker"] == "false"
    assert values["needs_e2e"] == "false"
    assert values["has_execution"] == "true"


def test_identical_tree_carry_requests_no_setup(
    verifier: ModuleType,
    tmp_path: Path,
) -> None:
    output = tmp_path / "github-output.txt"
    plan = verifier.resolve_selection(
        verifier_args(plan=True, carry_all=True, baseline_proven=True)
    )

    verifier.write_plan_outputs(plan, output)

    values = dict(
        line.split("=", maxsplit=1) for line in output.read_text(encoding="utf-8").splitlines()
    )
    assert values["groups"] == ""
    assert values["carried_groups"] == ",".join(verifier.VERIFICATION_GROUPS)
    assert values["skipped_groups"] == ""
    assert values["docker_groups"] == ""
    assert values["has_execution"] == "false"
    assert values["needs_node"] == "false"
    assert values["needs_api"] == "false"
    assert values["needs_ml"] == "false"
    assert values["needs_docker"] == "false"


def test_identical_tree_preserves_intentional_docker_skips(
    verifier: ModuleType,
    tmp_path: Path,
) -> None:
    output = tmp_path / "github-output.txt"
    plan = verifier.resolve_selection(
        verifier_args(
            plan=True,
            carry_all=True,
            baseline_proven=True,
            skipped_groups="compose,web-runtime,api-runtime,ml-runtime",
        )
    )

    verifier.write_plan_outputs(plan, output)

    values = dict(
        line.split("=", maxsplit=1) for line in output.read_text(encoding="utf-8").splitlines()
    )
    assert values["groups"] == ""
    assert values["carried_groups"] == ("contracts,docs,web-static,api-static,ml-static")
    assert values["skipped_groups"] == ("compose,web-runtime,api-runtime,ml-runtime")
    assert values["has_execution"] == "false"
    assert values["needs_docker"] == "false"


def test_docs_group_does_not_require_unrelated_toolchains(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    labels: list[str] = []
    monkeypatch.setattr(
        verifier,
        "parse_args",
        lambda: verifier_args(groups="docs"),
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
        lambda: verifier_args(groups="unknown"),
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
        pnpm="pnpm",
        uv="uv",
        docker="docker",
    )

    assert "Prove the Web container is healthy and non-root" in labels
    assert "Run API unit and real-service integration tests" not in labels
    assert "Prove the real ML worker and result-event boundary" not in labels


def test_api_runtime_owns_result_consumer_proof(
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
        groups=frozenset({"api-runtime"}),
        pnpm="pnpm",
        uv="uv",
        docker="docker",
    )

    assert "Prove API-owned result-event consumption and terminal persistence" in labels
    assert "Prove the real ML worker and result-event boundary" not in labels


def test_complete_compose_readiness_requires_exactly_eight_running_services(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_diagnostics = False

    def completed(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=("\n".join(sorted(verifier.EXPECTED_COMPOSE_SERVICES)) + "\n").encode(),
        )

    def capture(**_kwargs: object) -> None:
        nonlocal observed_diagnostics
        observed_diagnostics = True

    monkeypatch.setattr(verifier.subprocess, "run", completed)
    monkeypatch.setattr(verifier, "capture_runtime_diagnostic", capture)

    verifier.prove_complete_compose_readiness("docker")

    assert observed_diagnostics


def test_e2e_correlation_proof_requires_both_paths_in_every_service(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    completed_correlation = "11111111-1111-4111-8111-111111111111"
    failed_correlation = "22222222-2222-4222-8222-222222222222"
    evidence = {
        "completed": {
            "uploadCorrelation": {
                "request": completed_correlation,
                "response": completed_correlation,
            }
        },
        "failed": {
            "uploadCorrelation": {
                "request": failed_correlation,
                "response": failed_correlation,
            }
        },
    }
    (tmp_path / "e2e-result.json").write_text(json.dumps(evidence), encoding="utf-8")

    def completed(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            args=["docker"],
            returncode=0,
            stdout=f"{completed_correlation}\n{failed_correlation}\n".encode(),
        )

    monkeypatch.setattr(verifier, "ARTIFACT_DIRECTORY", tmp_path)
    monkeypatch.setattr(verifier.subprocess, "run", completed)

    verifier.prove_e2e_correlation("docker")

    proof = json.loads((tmp_path / "e2e-correlation-proof.json").read_text(encoding="utf-8"))
    assert set(proof) == {"api-outbox", "ml-worker", "api-events"}
    assert all(all(observations.values()) for observations in proof.values())


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
