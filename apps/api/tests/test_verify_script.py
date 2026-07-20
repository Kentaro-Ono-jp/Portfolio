from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
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
        "close_baseline_gaps": False,
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


@pytest.fixture
def ci_planner(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    scripts = REPOSITORY_ROOT / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    path = scripts / "plan_ci.py"
    specification = importlib.util.spec_from_file_location("portfolio_plan_ci", path)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def ci_context(ci_planner: ModuleType, **overrides: str) -> object:
    values = {
        "event_name": "pull_request",
        "event_action": "opened",
        "pr_base_sha": "1" * 40,
        "pr_head_sha": "2" * 40,
        "pr_author": "contributor",
        "before_sha": "0" * 40,
        "current_sha": "2" * 40,
        "actor": "contributor",
        "repository_owner": "owner",
        "repository": "owner/repository",
    }
    values.update(overrides)
    return ci_planner.CIContext(**values)


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
        baseline_proven=True,
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


def test_explicit_carried_groups_require_proven_baseline(verifier: ModuleType) -> None:
    with pytest.raises(RuntimeError, match="requires --baseline-proven"):
        verifier.resolve_selection(verifier_args(groups="docs", carried_groups="contracts"))


def test_carried_runtime_group_requires_covered_dependencies(
    verifier: ModuleType,
) -> None:
    with pytest.raises(ValueError, match="Carried group api-runtime"):
        verifier.resolve_selection(
            verifier_args(
                groups="docs",
                carried_groups="api-runtime",
                baseline_proven=True,
            )
        )


def test_static_only_rejects_silently_ignored_skip_input(verifier: ModuleType) -> None:
    with pytest.raises(RuntimeError, match="--skipped-groups is only valid"):
        verifier.resolve_selection(verifier_args(static_only=True, skipped_groups="compose"))


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
    follow_up = verifier.apply_skip_lineage(
        follow_up,
        baseline_skipped_groups=initial.skipped_groups,
        current_skipped_groups=initial.skipped_groups,
    )

    assert follow_up.groups == {"docs"}
    assert follow_up.carried_groups == {
        "contracts",
        "web-static",
        "api-static",
        "ml-static",
    }
    assert follow_up.skipped_groups == verifier.DOCKER_GROUPS


def test_second_docs_follow_up_rejects_missing_inherited_skip_trailer(
    verifier: ModuleType,
) -> None:
    inherited_skips = verifier.DOCKER_GROUPS
    first_follow_up = verifier.plan_for_paths(
        ["docs/ai/README.md"],
        baseline_proven=True,
        baseline_skipped_groups=inherited_skips,
    )
    first_follow_up = verifier.apply_skip_lineage(
        first_follow_up,
        baseline_skipped_groups=inherited_skips,
        current_skipped_groups=inherited_skips,
    )
    second_follow_up = verifier.plan_for_paths(
        ["docs/ai/PR_REVIEW.md"],
        baseline_proven=True,
        baseline_skipped_groups=first_follow_up.skipped_groups,
    )

    with pytest.raises(RuntimeError, match="Current Verification-Skip omits"):
        verifier.apply_skip_lineage(
            second_follow_up,
            baseline_skipped_groups=first_follow_up.skipped_groups,
            current_skipped_groups=frozenset(),
        )


def test_current_skip_cannot_replace_carried_baseline_evidence(
    verifier: ModuleType,
) -> None:
    plan = verifier.plan_for_paths(
        ["docs/ai/README.md"],
        baseline_proven=True,
    )

    with pytest.raises(RuntimeError, match="Cannot relabel carried baseline evidence"):
        verifier.move_groups_to_skipped(plan, frozenset({"compose"}))


def test_current_skip_cannot_break_selected_group_dependencies(
    verifier: ModuleType,
) -> None:
    plan = verifier.plan_for_paths(["scripts/verify.py"], baseline_proven=True)

    with pytest.raises(RuntimeError, match="Skipped groups break selected dependencies"):
        verifier.move_groups_to_skipped(plan, frozenset({"compose"}))


def test_cross_boundary_rename_selects_old_and_new_path_groups(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def completed(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert "--name-status" in command
        assert "--find-renames" in command
        assert "--find-copies" in command
        assert "--find-copies-harder" in command
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


def test_real_git_cross_boundary_copy_selects_source_and_destination_groups(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "copy-repository"
    repository.mkdir()

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip()

    git("init")
    git("config", "user.name", "Verification Test")
    git("config", "user.email", "verification@example.invalid")
    source = repository / "apps/api/src/reactorfront_api/copied.py"
    source.parent.mkdir(parents=True)
    source.write_text("COPY_BOUNDARY = 'api-to-docs'\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "Add API source")
    base = git("rev-parse", "HEAD")

    destination = repository / "docs/copied.md"
    destination.parent.mkdir(parents=True)
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "Copy API source into docs")

    monkeypatch.setattr(verifier, "REPOSITORY_ROOT", repository)
    plan = verifier.plan_from_git(base=base)

    assert plan.changed_files == (
        "apps/api/src/reactorfront_api/copied.py",
        "docs/copied.md",
    )
    assert plan.groups == {"docs", "compose", "api-static", "api-runtime"}


def test_baseline_skips_require_a_diff_plan(verifier: ModuleType) -> None:
    with pytest.raises(RuntimeError, match="only valid with --base, --staged"):
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

    assert len(inventory) == 36
    assert len(verifier.selected_test_files(plan.groups)) == 9
    assert "Verification groups: 1/9 selected" in verifier.plan_lines(plan)
    assert "Test files: 9/36 selected" in verifier.plan_lines(plan)


def test_partial_web_runtime_does_not_count_unexecuted_browser_e2e(
    verifier: ModuleType,
) -> None:
    partial = verifier.expand_group_dependencies({"web-runtime"})

    assert not any(path.startswith("tests/e2e/") for path in verifier.selected_test_files(partial))
    assert any(
        path.startswith("tests/e2e/") for path in verifier.selected_test_files(verifier.ALL_GROUPS)
    )


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
            baseline_skipped_groups="compose,web-runtime,api-runtime,ml-runtime",
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


def test_identical_tree_rejects_missing_current_skip_restatement(
    verifier: ModuleType,
) -> None:
    with pytest.raises(RuntimeError, match="Current Verification-Skip omits"):
        verifier.resolve_selection(
            verifier_args(
                plan=True,
                carry_all=True,
                baseline_proven=True,
                baseline_skipped_groups=("compose,web-runtime,api-runtime,ml-runtime"),
            )
        )


def test_identical_tree_rejects_new_skip_without_baseline_gap(
    verifier: ModuleType,
) -> None:
    with pytest.raises(RuntimeError, match="Cannot relabel carried baseline evidence"):
        verifier.resolve_selection(
            verifier_args(
                plan=True,
                carry_all=True,
                baseline_proven=True,
                skipped_groups="compose",
            )
        )


def test_static_only_selection_contains_no_docker_groups(verifier: ModuleType) -> None:
    plan = verifier.resolve_selection(verifier_args(static_only=True))

    assert plan.groups == verifier.LOCAL_STATIC_GROUPS
    assert not plan.groups & verifier.DOCKER_GROUPS


def test_closing_partial_baseline_gap_reruns_dependent_evidence(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        verifier,
        "plan_from_git",
        lambda **kwargs: verifier.plan_for_paths(
            ["docs/ai/README.md"],
            base=kwargs["base"],
            baseline_proven=kwargs["baseline_proven"],
            baseline_skipped_groups=kwargs["baseline_skipped_groups"],
        ),
    )

    plan = verifier.resolve_selection(
        verifier_args(
            base="1" * 40,
            baseline_proven=True,
            baseline_skipped_groups="compose",
            close_baseline_gaps=True,
        )
    )

    assert plan.groups >= verifier.DOCKER_GROUPS
    assert not verifier.DOCKER_GROUPS & plan.carried_groups


def test_closing_baseline_gaps_cannot_reskip_current_groups(
    verifier: ModuleType,
) -> None:
    with pytest.raises(RuntimeError, match="cannot be combined"):
        verifier.resolve_selection(
            verifier_args(
                base="1" * 40,
                baseline_proven=True,
                baseline_skipped_groups="compose",
                close_baseline_gaps=True,
                skipped_groups="compose",
            )
        )


def test_static_only_main_never_resolves_docker(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    required: list[str] = []
    monkeypatch.setattr(verifier, "ARTIFACT_DIRECTORY", tmp_path / "artifacts")
    monkeypatch.setattr(verifier, "parse_args", lambda: verifier_args(static_only=True))
    monkeypatch.setattr(
        verifier,
        "require_command",
        lambda command: required.append(command) or command,
    )

    def checks(**arguments: object) -> list[tuple[str, list[str]]]:
        assert arguments["docker"] == ""
        assert arguments["groups"] == verifier.LOCAL_STATIC_GROUPS
        return []

    monkeypatch.setattr(verifier, "static_checks", checks)
    monkeypatch.setattr(
        verifier,
        "run_runtime_checks",
        lambda **_arguments: pytest.fail("static-only started runtime checks"),
    )

    assert verifier.main() == 0
    assert required == ["pnpm", "uv"]


def test_plan_accepts_explicit_non_docker_groups(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        verifier,
        "parse_args",
        lambda: verifier_args(plan=True, groups="docs"),
    )
    monkeypatch.setattr(
        verifier,
        "static_checks",
        lambda **_arguments: pytest.fail("a plan must not execute checks"),
    )

    assert verifier.main() == 0


def test_invalid_carried_evidence_is_reported_without_traceback(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        verifier,
        "parse_args",
        lambda: verifier_args(
            groups="docs",
            carried_groups="api-runtime",
            baseline_proven=True,
        ),
    )

    assert verifier.main() == 1
    assert "Carried group api-runtime" in capsys.readouterr().err


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


def test_artifact_directory_failure_returns_a_clean_failure(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("blocked", encoding="utf-8")
    monkeypatch.setattr(verifier, "ARTIFACT_DIRECTORY", blocking_file / "artifacts")
    monkeypatch.setattr(verifier, "parse_args", lambda: verifier_args(groups="docs"))

    assert verifier.main() == 1
    assert "Verification failed" in capsys.readouterr().err


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


def test_diagnostics_failure_preserves_main_failure_and_cleanup(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cleanup_called = False

    def fail_runtime(**_commands: str) -> None:
        raise RuntimeError("primary verification fault")

    def fail_diagnostics(_docker: str) -> None:
        raise OSError("diagnostic transport fault")

    def cleanup(_docker: str) -> None:
        nonlocal cleanup_called
        cleanup_called = True

    configure_runtime_verification(
        verifier,
        monkeypatch,
        runtime_check=fail_runtime,
        cleanup=cleanup,
    )
    monkeypatch.setattr(verifier, "show_runtime_diagnostics", fail_diagnostics)

    assert verifier.main() == 1
    assert cleanup_called
    error_output = capsys.readouterr().err
    assert "primary verification fault" in error_output
    assert "Runtime diagnostics failed: diagnostic transport fault" in error_output


def test_verifier_returns_failure_when_cleanup_command_is_missing(
    verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_cleanup(_docker: str) -> None:
        raise OSError("docker executable disappeared")

    configure_runtime_verification(
        verifier,
        monkeypatch,
        runtime_check=lambda **_commands: None,
        cleanup=fail_cleanup,
    )

    assert verifier.main() == 1


def test_external_pr_executes_trusted_base_gaps_and_ignores_current_skip(
    ci_planner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inherited = "compose,web-runtime,api-runtime,ml-runtime"
    monkeypatch.setattr(ci_planner, "latest_run_succeeded", lambda *_args: True)
    monkeypatch.setattr(
        ci_planner,
        "trailer_value",
        lambda _repository, sha, _key: (
            inherited
            if sha == "1" * 40
            else pytest.fail("external current trailer must not be trusted")
        ),
    )
    request = ci_planner.select_ci_plan(ci_context(ci_planner))

    assert request.baseline_skipped_groups == inherited
    assert request.current_skipped_groups == ""
    assert request.close_baseline_gaps
    monkeypatch.setattr(
        ci_planner.verify,
        "plan_from_git",
        lambda **kwargs: ci_planner.verify.plan_for_paths(
            ["docs/ai/README.md"],
            base=kwargs["base"],
            baseline_proven=kwargs["baseline_proven"],
            baseline_skipped_groups=kwargs["baseline_skipped_groups"],
        ),
    )
    plan = request.resolve()

    assert plan.groups >= ci_planner.verify.DOCKER_GROUPS
    assert not ci_planner.verify.DOCKER_GROUPS & plan.carried_groups


def test_external_pr_synchronize_replans_from_trusted_pr_base(
    ci_planner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ci_planner, "latest_run_succeeded", lambda *_args: True)
    observed: list[str] = []

    def trailer(_repository: str, sha: str, _key: str) -> str:
        observed.append(sha)
        return ""

    monkeypatch.setattr(ci_planner, "trailer_value", trailer)

    request = ci_planner.select_ci_plan(
        ci_context(
            ci_planner,
            event_action="synchronize",
            before_sha="3" * 40,
        )
    )

    assert request.base == "1" * 40
    assert observed == ["1" * 40]
    assert request.baseline_skipped_groups == ""
    assert request.current_skipped_groups == ""
    assert not request.close_baseline_gaps


def test_external_pr_stops_before_setup_without_successful_base(
    ci_planner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ci_planner, "latest_run_succeeded", lambda *_args: False)

    with pytest.raises(RuntimeError, match="no checks or Docker were started"):
        ci_planner.select_ci_plan(ci_context(ci_planner))


def test_owner_pr_without_successful_base_uses_cold_full_and_current_skip(
    ci_planner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ci_planner, "latest_run_succeeded", lambda *_args: False)
    inherited = "compose,web-runtime,api-runtime,ml-runtime"
    monkeypatch.setattr(ci_planner, "trailer_value", lambda *_args: inherited)

    request = ci_planner.select_ci_plan(ci_context(ci_planner, pr_author="OWNER", actor="OWNER"))

    assert request.full
    assert not request.baseline_proven
    assert request.current_skipped_groups == inherited


def test_owner_pr_synchronize_reads_baseline_and_current_trailers(
    ci_planner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []
    monkeypatch.setattr(ci_planner, "latest_run_succeeded", lambda *_args: True)

    def trailer(_repository: str, sha: str, _key: str) -> str:
        observed.append(sha)
        return "compose" if sha == "3" * 40 else ""

    monkeypatch.setattr(ci_planner, "trailer_value", trailer)
    request = ci_planner.select_ci_plan(
        ci_context(
            ci_planner,
            event_action="synchronize",
            before_sha="3" * 40,
            pr_author="owner",
            actor="owner",
        )
    )

    assert observed == ["3" * 40, "2" * 40]
    assert request.baseline_skipped_groups == "compose"


def test_tree_identical_merge_requires_current_skip_restatement(
    ci_planner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inherited = "compose,web-runtime,api-runtime,ml-runtime"
    context = ci_context(
        ci_planner,
        event_name="push",
        event_action="",
        current_sha="4" * 40,
        before_sha="1" * 40,
        actor="owner",
    )
    monkeypatch.setattr(ci_planner, "merged_pr_for_commit", lambda *_args: ("2" * 40, "owner"))
    monkeypatch.setattr(ci_planner, "remote_commit_tree", lambda *_args: "a" * 40)
    monkeypatch.setattr(ci_planner, "local_commit_tree", lambda *_args: "a" * 40)
    monkeypatch.setattr(ci_planner, "latest_run_succeeded", lambda *_args: True)
    monkeypatch.setattr(
        ci_planner,
        "trailer_value",
        lambda _repository, sha, _key: inherited if sha == "2" * 40 else "",
    )

    request = ci_planner.select_ci_plan(context)

    assert request.carry_all
    assert request.baseline_skipped_groups == inherited
    assert request.current_skipped_groups == ""
    with pytest.raises(RuntimeError, match="Current Verification-Skip omits"):
        request.resolve()


def test_failed_tree_identical_lineage_cannot_seed_the_next_push(
    ci_planner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inherited = "compose,web-runtime,api-runtime,ml-runtime"
    merge_sha = "4" * 40
    merge_context = ci_context(
        ci_planner,
        event_name="push",
        event_action="",
        current_sha=merge_sha,
        before_sha="1" * 40,
        actor="owner",
    )
    monkeypatch.setattr(ci_planner, "merged_pr_for_commit", lambda *_args: ("2" * 40, "owner"))
    monkeypatch.setattr(ci_planner, "remote_commit_tree", lambda *_args: "a" * 40)
    monkeypatch.setattr(ci_planner, "local_commit_tree", lambda *_args: "a" * 40)
    monkeypatch.setattr(ci_planner, "latest_run_succeeded", lambda *_args: True)
    monkeypatch.setattr(
        ci_planner,
        "trailer_value",
        lambda _repository, sha, _key: inherited if sha == "2" * 40 else "",
    )

    with pytest.raises(RuntimeError, match="Current Verification-Skip omits"):
        ci_planner.select_ci_plan(merge_context).resolve()

    next_context = ci_context(
        ci_planner,
        event_name="push",
        event_action="",
        current_sha="5" * 40,
        before_sha=merge_sha,
        actor="owner",
    )
    monkeypatch.setattr(ci_planner, "merged_pr_for_commit", lambda *_args: None)
    monkeypatch.setattr(ci_planner, "latest_run_succeeded", lambda *_args: False)

    with pytest.raises(RuntimeError, match="lacks a latest successful Verify run"):
        ci_planner.select_ci_plan(next_context)


def test_tree_identical_merge_preserves_repeated_skip_lineage(
    ci_planner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inherited = "compose,web-runtime,api-runtime,ml-runtime"
    context = ci_context(
        ci_planner,
        event_name="push",
        event_action="",
        current_sha="4" * 40,
        before_sha="1" * 40,
        actor="owner",
    )
    monkeypatch.setattr(ci_planner, "merged_pr_for_commit", lambda *_args: ("2" * 40, "owner"))
    monkeypatch.setattr(ci_planner, "remote_commit_tree", lambda *_args: "a" * 40)
    monkeypatch.setattr(ci_planner, "local_commit_tree", lambda *_args: "a" * 40)
    monkeypatch.setattr(ci_planner, "latest_run_succeeded", lambda *_args: True)
    monkeypatch.setattr(ci_planner, "trailer_value", lambda *_args: inherited)

    plan = ci_planner.select_ci_plan(context).resolve()

    assert plan.groups == set()
    assert plan.carried_groups == ci_planner.verify.LOCAL_STATIC_GROUPS
    assert plan.skipped_groups == ci_planner.verify.DOCKER_GROUPS


def test_normal_main_push_preserves_baseline_skip_lineage(
    ci_planner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inherited = "compose,web-runtime,api-runtime,ml-runtime"
    context = ci_context(
        ci_planner,
        event_name="push",
        event_action="",
        current_sha="4" * 40,
        before_sha="1" * 40,
        actor="OWNER",
    )
    monkeypatch.setattr(ci_planner, "merged_pr_for_commit", lambda *_args: None)
    monkeypatch.setattr(ci_planner, "latest_run_succeeded", lambda *_args: True)
    monkeypatch.setattr(
        ci_planner,
        "trailer_value",
        lambda _repository, sha, _key: inherited if sha == "1" * 40 else "",
    )
    monkeypatch.setattr(
        ci_planner.verify,
        "plan_from_git",
        lambda **kwargs: ci_planner.verify.plan_for_paths(
            ["docs/ai/README.md"],
            base=kwargs["base"],
            baseline_proven=kwargs["baseline_proven"],
            baseline_skipped_groups=kwargs["baseline_skipped_groups"],
        ),
    )

    request = ci_planner.select_ci_plan(context)

    with pytest.raises(RuntimeError, match="Current Verification-Skip omits"):
        request.resolve()


def test_external_merged_pr_uses_main_baseline_instead_of_carry_all(
    ci_planner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = ci_context(
        ci_planner,
        event_name="push",
        event_action="",
        current_sha="4" * 40,
        before_sha="1" * 40,
        actor="owner",
    )
    monkeypatch.setattr(
        ci_planner,
        "merged_pr_for_commit",
        lambda *_args: ("2" * 40, "contributor"),
    )
    monkeypatch.setattr(ci_planner, "remote_commit_tree", lambda *_args: "a" * 40)
    monkeypatch.setattr(ci_planner, "latest_run_succeeded", lambda *_args: True)
    monkeypatch.setattr(ci_planner, "trailer_value", lambda *_args: "")

    request = ci_planner.select_ci_plan(context)

    assert not request.carry_all
    assert request.base == "1" * 40


def test_github_error_escapes_workflow_command_characters(
    ci_planner: ModuleType,
) -> None:
    assert ci_planner.github_error("bad%line\r\nnext") == ("::error::bad%25line%0D%0Anext")


def test_non_owner_cannot_dispatch_full_verification(
    ci_planner: ModuleType,
) -> None:
    with pytest.raises(RuntimeError, match="Only the repository owner"):
        ci_planner.select_ci_plan(
            ci_context(
                ci_planner,
                event_name="workflow_dispatch",
                event_action="",
            )
        )


def test_non_owner_push_cannot_establish_main_evidence(
    ci_planner: ModuleType,
) -> None:
    with pytest.raises(RuntimeError, match="Only the repository owner"):
        ci_planner.select_ci_plan(
            ci_context(
                ci_planner,
                event_name="push",
                event_action="",
                current_sha="4" * 40,
            )
        )


def test_ci_planner_main_writes_complete_dispatch_plan(
    ci_planner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "output.txt"
    summary = tmp_path / "summary.md"
    environment = {
        "EVENT_NAME": "workflow_dispatch",
        "EVENT_ACTION": "",
        "PR_BASE_SHA": "",
        "PR_HEAD_SHA": "",
        "PR_AUTHOR": "",
        "BEFORE_SHA": "",
        "CURRENT_SHA": "4" * 40,
        "ACTOR": "owner",
        "REPOSITORY_OWNER": "owner",
        "REPOSITORY": "owner/repository",
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    assert ci_planner.main() == 0
    output_values = dict(
        line.split("=", maxsplit=1) for line in output.read_text(encoding="utf-8").splitlines()
    )
    assert output_values["groups"] == ",".join(ci_planner.verify.VERIFICATION_GROUPS)
    assert output_values["carried_groups"] == ""
    assert output_values["skipped_groups"] == ""
    assert output_values["needs_docker"] == "true"
    summary_text = summary.read_text(encoding="utf-8")
    assert "Verification groups: 9/9 selected" in summary_text
    assert "Selection baseline: owner-dispatched full verification" in summary_text
