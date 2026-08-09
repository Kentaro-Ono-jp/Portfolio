from __future__ import annotations

import importlib.util
import subprocess
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def documentation_checker() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts" / "check_docs.py"
    specification = importlib.util.spec_from_file_location("portfolio_check_docs", path)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_repository_owned_governance_invariants_pass(
    documentation_checker: ModuleType,
) -> None:
    assert documentation_checker.governance_failures() == []


def test_merge_status_check_policy_is_machine_guarded(
    documentation_checker: ModuleType,
) -> None:
    merge = Path("ips-microkernel/procedures/merge.md")
    contract = documentation_checker.MERGE_STATUS_CHECK_FRAGMENTS
    required_text = documentation_checker.REQUIRED_GOVERNANCE_TEXT

    assert contract.keys() == {merge}
    assert all(fragment in required_text[merge] for fragment in contract[merge])


def test_merge_status_check_policy_rejects_each_weakened_boundary(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    relative_path = Path("ips-microkernel/procedures/merge.md")
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    normalized = " ".join(source.split())
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    for fragment in documentation_checker.MERGE_STATUS_CHECK_FRAGMENTS[relative_path]:
        assert fragment in normalized
        target.write_text(
            normalized.replace(
                fragment,
                "weakened merge status-check boundary",
                1,
            ),
            encoding="utf-8",
        )
        failures: list[str] = []

        documentation_checker._validate_required_governance_text(
            failures,
            {relative_path: (fragment,)},
        )

        assert failures == [
            f"{relative_path.as_posix()}: missing governance invariant {fragment!r}"
        ]


@pytest.mark.parametrize(
    ("content", "target"),
    (
        ("[origin][human]\n\n[human]: README.md\n", "README.md"),
        ("[origin][]\n\n[origin]:\n    <README.md>\n", "README.md"),
        ("[Human Label]\n\n[human\n label]: README.md\n", "README.md"),
        ("[human]\n\n> [human]:\n> README.md\n", "README.md"),
        ("[Human Label]\n\n> [human\n> label]: README.md\n", "README.md"),
        ('<a class="origin" href="README.md">origin</a>\n', "README.md"),
    ),
)
def test_markdown_link_targets_supports_gfm_reference_forms_and_layouts(
    documentation_checker: ModuleType,
    content: str,
    target: str,
) -> None:
    assert documentation_checker.markdown_link_targets(content) == [target]


@pytest.mark.parametrize(
    "target",
    (
        "README.md?plain=1",
        "README.md#architecture",
        "README&#46;md",
        r"README\.md",
    ),
)
def test_local_target_normalizes_rendered_url_aliases(
    documentation_checker: ModuleType,
    target: str,
) -> None:
    assert documentation_checker.local_target(target) == "README.md"


def test_progressive_routing_covers_the_complete_guidance_surface(
    documentation_checker: ModuleType,
) -> None:
    routes = documentation_checker.REQUIRED_ROUTE_LINKS
    roles = documentation_checker.IPS_FILE_ROLES

    assert routes[Path("GIT_AGENTS.md")] == (
        Path("AI_GUIDANCE.md"),
        Path("ips-microkernel/work-router.md"),
        Path("ips-microkernel/ci/router.md"),
    )
    assert (
        Path("ips-microkernel/procedures/focus.md")
        in routes[Path("ips-microkernel/work-router.md")]
    )
    assert (
        Path("ips-microkernel/procedures/governance-reconcile.md")
        in routes[Path("ips-microkernel/work-router.md")]
    )
    assert (
        Path("ips-microkernel/ci/exceptions/markdown-only.md")
        not in routes[Path("ips-microkernel/ci/procedures/preflight.md")]
    )
    assert (
        Path("ips-microkernel/ci/knowledge/selector.md")
        in routes[Path("ips-microkernel/ci/procedures/preflight.md")]
    )
    assert (
        Path("ips-microkernel/selectors/governance-knowledge.md")
        not in routes[Path("ips-microkernel/procedures/implement.md")]
    )
    assert (
        Path("ips-microkernel/selectors/governance-knowledge.md")
        not in routes[Path("ips-microkernel/review/inspect.md")]
    )
    assert (
        Path("ips-microkernel/procedures/focus.md")
        in routes[Path("ips-microkernel/procedures/correct.md")]
    )
    assert (
        Path("ips-microkernel/procedures/adjudicate.md")
        in routes[Path("ips-microkernel/work-router.md")]
    )
    assert (
        Path("ips-microkernel/procedures/adjudicate.md")
        not in routes[Path("ips-microkernel/review/router.md")]
    )
    assert (
        Path("ips-microkernel/procedures/merge.md")
        in routes[Path("ips-microkernel/procedures/correct.md")]
    )
    scratchpad = Path("ips-microkernel/references/focus-scratchpad.md")
    assert scratchpad in routes[Path("ips-microkernel/work-router.md")]
    assert scratchpad in routes[Path("ips-microkernel/references/authority.md")]
    assert roles[scratchpad] == "reference"
    assert set(roles.values()) == {
        "router",
        "selector",
        "procedure",
        "reference",
        "knowledge",
        "exception",
    }


def test_every_canonical_rule_has_one_declared_owner(
    documentation_checker: ModuleType,
) -> None:
    owners = documentation_checker.CANONICAL_RULE_OWNERS

    assert len(owners) == len(set(owners))
    assert len(owners.values()) == len(set(owners.values()))
    assert owners["actor-authority"] == Path("ips-microkernel/references/authority.md")
    assert owners["focus-scratchpad"] == Path("ips-microkernel/references/focus-scratchpad.md")
    assert owners["ci-markdown-only-exception"] == Path(
        "ips-microkernel/ci/exceptions/markdown-only.md"
    )
    assert owners["governance-knowledge-selection"] == Path(
        "ips-microkernel/selectors/governance-knowledge.md"
    )
    assert owners["governance-knowledge-reconciliation"] == Path(
        "ips-microkernel/procedures/governance-reconcile.md"
    )
    assert owners["review-adjudication"] == Path("ips-microkernel/procedures/adjudicate.md")
    assert owners["knowledge-curation"] == Path("ips-microkernel/procedures/curate-knowledge.md")
    assert owners["implementation-correction-ledger"] == Path(
        "ips-microkernel/knowledge/correction-ledger.md"
    )
    assert owners["stage-b-pre-review-checklist"] == Path("ips-microkernel/knowledge/behavior.md")
    assert owners["ci-knowledge-identity"] == Path("ips-microkernel/ci/knowledge/identity.md")
    assert owners["ci-knowledge-framework-runtime"] == Path(
        "ips-microkernel/ci/knowledge/framework-runtime.md"
    )


def test_owner_authorized_focus_scratchpad_contract_is_complete(
    documentation_checker: ModuleType,
) -> None:
    scratchpad = Path("ips-microkernel/references/focus-scratchpad.md")
    adr = Path("ips-microkernel/adr/0020-authorize-owner-controlled-focus-scratchpad.md")
    required_text = documentation_checker.REQUIRED_GOVERNANCE_TEXT
    source = (REPOSITORY_ROOT / scratchpad).read_text(encoding="utf-8")
    ignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
    tracked_scratch = subprocess.run(
        ["git", "ls-files", "--", ".noel-focus"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert scratchpad in documentation_checker.REQUIRED_GOVERNANCE_FILES
    assert adr in documentation_checker.REQUIRED_GOVERNANCE_FILES
    assert ".noel-focus/" in ignore.splitlines()
    assert tracked_scratch == []
    assert "requires no trigger, justification, or record" in " ".join(source.split())
    assert "create, read, update, execute, reorganize, retain, or delete" in " ".join(
        source.split()
    )
    assert "No summary, deletion, or reconciliation is required" in " ".join(source.split())
    assert all(
        fragment in required_text[scratchpad]
        for fragment in (
            "delegates full discretion over `.noel-focus/`",
            "repository owner accepts responsibility",
            "Any effect outside `.noel-focus/` remains governed",
        )
    )


@pytest.mark.parametrize(
    ("relative_path", "fragment"),
    (
        (
            Path("ips-microkernel/work-router.md"),
            "Open that reference only after deciding to use it",
        ),
        (
            Path("ips-microkernel/references/authority.md"),
            "effects outside the delegated directory retain their ordinary authority",
        ),
        (
            Path("ips-microkernel/references/focus-scratchpad.md"),
            "requires no trigger, justification, or record",
        ),
        (
            Path("ips-microkernel/references/focus-scratchpad.md"),
            "No summary, deletion, or reconciliation is required",
        ),
        (
            Path("ips-microkernel/references/focus-scratchpad.md"),
            "Their existence alone does not make them repository evidence",
        ),
        (
            Path("ips-microkernel/adr/0020-authorize-owner-controlled-focus-scratchpad.md"),
            "has no required trigger, layout, template, naming scheme, size",
        ),
        (Path(".gitignore"), ".noel-focus/"),
    ),
)
def test_focus_scratchpad_contract_rejects_a_weakened_boundary(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_path: Path,
    fragment: str,
) -> None:
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    normalized = " ".join(source.split())
    assert fragment in normalized
    destination = tmp_path / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        normalized.replace(fragment, "weakened scratchpad boundary"),
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_required_governance_text(
        failures,
        {relative_path: (fragment,)},
    )

    assert failures == [f"{relative_path.as_posix()}: missing governance invariant {fragment!r}"]


def test_stage_a_stage_b_and_ci_playbook_are_separately_routed(
    documentation_checker: ModuleType,
) -> None:
    routes = documentation_checker.REQUIRED_ROUTE_LINKS
    roles = documentation_checker.IPS_FILE_ROLES
    stage_a = Path("ips-microkernel/knowledge/correction-ledger.md")
    stage_b = Path("ips-microkernel/knowledge/behavior.md")
    identity = Path("ips-microkernel/ci/knowledge/identity.md")
    framework_runtime = Path("ips-microkernel/ci/knowledge/framework-runtime.md")
    implement = Path("ips-microkernel/procedures/implement.md")
    publish = Path("ips-microkernel/procedures/publish.md")
    preflight = Path("ips-microkernel/ci/procedures/preflight.md")
    correction = Path("ips-microkernel/procedures/correct.md")
    playbook_selector = Path("ips-microkernel/ci/knowledge/selector.md")
    failure_triage = Path("ips-microkernel/ci/procedures/failure-triage.md")
    governance_selector = Path("ips-microkernel/selectors/governance-knowledge.md")

    assert roles[stage_a] == roles[stage_b] == roles[identity] == "knowledge"
    assert roles[framework_runtime] == "knowledge"
    assert stage_a not in routes[implement]
    assert stage_a not in routes[preflight]
    assert stage_a in routes[correction]
    assert stage_a in routes[failure_triage]
    assert stage_b not in routes[implement]
    assert stage_b not in routes[preflight]
    assert stage_b in routes[publish]
    assert stage_b in routes[correction]
    assert stage_a not in routes[governance_selector]
    assert stage_b not in routes[governance_selector]
    assert identity in routes[playbook_selector]
    assert framework_runtime in routes[playbook_selector]
    assert playbook_selector in routes[preflight]
    assert playbook_selector in routes[failure_triage]
    assert Path("ips-microkernel/ci/router.md") in routes[publish]


def test_stage_a_occurrences_allow_duplicate_mistakes(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    record = tmp_path / "ips-microkernel" / "knowledge" / "corrections" / "pr-0064.md"
    record.parent.mkdir(parents=True)
    occurrence = """\
- **PR:** PR #64
- **Mistake:** The same implementation mistake.
- **Correction:** The same concrete correction.
"""
    record.write_text(
        "# PR #64 implementation-correction occurrences\n\n"
        "<!-- ips-data: implementation-correction-occurrences -->\n\n"
        f"### Occurrence 1\n\n{occurrence}\n"
        f"### Occurrence 2\n\n{occurrence}",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_stage_a_occurrence_records(failures)

    assert failures == []


def test_stage_a_occurrence_rejects_missing_required_field(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    record = tmp_path / "ips-microkernel" / "knowledge" / "corrections" / "pr-0064.md"
    record.parent.mkdir(parents=True)
    record.write_text(
        "# PR #64 implementation-correction occurrences\n\n"
        "<!-- ips-data: implementation-correction-occurrences -->\n\n"
        "### Occurrence 1\n\n"
        "- **PR:** PR #64\n"
        "- **Mistake:** Missing correction.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_stage_a_occurrence_records(failures)

    assert any("exactly PR, Mistake, Correction" in failure for failure in failures)


def test_stage_a_occurrence_rejects_an_unknown_field(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    record = tmp_path / "ips-microkernel" / "knowledge" / "corrections" / "pr-0064.md"
    record.parent.mkdir(parents=True)
    record.write_text(
        "# PR #64 implementation-correction occurrences\n\n"
        "<!-- ips-data: implementation-correction-occurrences -->\n\n"
        "### Occurrence 1\n\n"
        "- **PR:** PR #64\n"
        "- **Mistake:** An observed mistake.\n"
        "- **Correction:** A concrete correction.\n"
        "- **Evidence:** Prohibited proof-style field.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_stage_a_occurrence_records(failures)

    assert any("exactly PR, Mistake, Correction" in failure for failure in failures)


@pytest.mark.parametrize("blank_field", ("PR", "Mistake", "Correction"))
def test_stage_a_occurrence_rejects_a_blank_required_value(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    blank_field: str,
) -> None:
    values = {
        "PR": "PR #64",
        "Mistake": "An observed mistake.",
        "Correction": "A concrete correction.",
    }
    values[blank_field] = ""
    record = tmp_path / "ips-microkernel" / "knowledge" / "corrections" / "pr-0064.md"
    record.parent.mkdir(parents=True)
    record.write_text(
        "# PR #64 implementation-correction occurrences\n\n"
        "<!-- ips-data: implementation-correction-occurrences -->\n\n"
        "### Occurrence 1\n\n"
        f"- **PR:** {values['PR']}\n"
        f"- **Mistake:** {values['Mistake']}\n"
        f"- **Correction:** {values['Correction']}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_stage_a_occurrence_records(failures)

    assert any("required fields must be non-empty" in failure for failure in failures)


def test_stage_b_rules_have_machine_detection_and_repair(
    documentation_checker: ModuleType,
) -> None:
    failures: list[str] = []

    documentation_checker._validate_stage_b_rules(failures)

    assert failures == []


def test_stage_b_rejects_a_duplicate_rule_title(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    relative_path = Path("ips-microkernel/knowledge/behavior.md")
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    duplicate = source.replace(
        "### Invalidate head-bound review evidence",
        "### Publish exact review endpoints",
        1,
    )
    destination = tmp_path / relative_path
    destination.parent.mkdir(parents=True)
    destination.write_text(duplicate, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_stage_b_rules(failures)

    assert any("duplicate Stage B rule titles" in failure for failure in failures)


def test_stage_b_rejects_an_unknown_field(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    relative_path = Path("ips-microkernel/knowledge/behavior.md")
    destination = tmp_path / relative_path
    destination.parent.mkdir(parents=True)
    destination.write_text(
        "# Stage B\n\n## Rules\n\n### Exact rule\n\n"
        "- **Trigger:** Before review.\n"
        "- **HEAD effect:** `neutral`\n"
        "- **Problem:** Invalid records pass.\n"
        "- **Detect:** Execute mutation probes.\n"
        "- **Pass:** Every invalid mutation fails.\n"
        "- **Repair:** Enforce the exact schema.\n"
        "- **Evidence:** Prohibited proof-style field.\n"
        "- **Origins:** PR #64.\n\n"
        "## Execution and correction\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_stage_b_rules(failures)

    assert any("must contain exactly Trigger" in failure for failure in failures)


@pytest.mark.parametrize(
    "blank_field",
    ("Trigger", "HEAD effect", "Problem", "Detect", "Pass", "Repair", "Origins"),
)
def test_stage_b_rejects_a_blank_required_value(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    blank_field: str,
) -> None:
    values = {
        "Trigger": "Before review.",
        "HEAD effect": "`neutral`",
        "Problem": "Invalid records pass.",
        "Detect": "Execute mutation probes.",
        "Pass": "Every invalid mutation fails.",
        "Repair": "Enforce the exact schema.",
        "Origins": "PR #64.",
    }
    values[blank_field] = ""
    relative_path = Path("ips-microkernel/knowledge/behavior.md")
    destination = tmp_path / relative_path
    destination.parent.mkdir(parents=True)
    destination.write_text(
        "# Stage B\n\n## Rules\n\n### Exact rule\n\n"
        + "".join(f"- **{field}:** {value}\n" for field, value in values.items())
        + "\n## Execution and correction\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_stage_b_rules(failures)

    assert any("required fields must be non-empty" in failure for failure in failures)


def test_ci_playbook_allows_duplicate_correction_records(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    leaf = tmp_path / "ips-microkernel" / "ci" / "knowledge" / "sample.md"
    leaf.parent.mkdir(parents=True)
    record = """\
### Repeated correction

- **Origin:** PR #64
- **Trigger:** Same trigger.
- **Mistake:** Same mistake.
- **Correction:** Same correction.
"""
    leaf.write_text(
        "# CI Playbook: sample corrections\n\n"
        "## Read when\n\nBefore remote push, read this leaf.\n\n"
        f"## Correction records\n\n{record}\n{record}\n"
        "## Return\n\nReturn to publication Gate A.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_ci_playbook_records(failures)

    assert failures == []


def test_ci_playbook_rejects_a_proof_style_field(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    leaf = tmp_path / "ips-microkernel" / "ci" / "knowledge" / "sample.md"
    leaf.parent.mkdir(parents=True)
    leaf.write_text(
        "# CI Playbook: sample corrections\n\n"
        "## Read when\n\nBefore remote push, read this leaf.\n\n"
        "## Correction records\n\n### Broken record\n\n"
        "- **Origin:** PR #64\n- **Trigger:** Trigger.\n"
        "- **Mistake:** Mistake.\n- **Correction:** Correction.\n"
        "- **Evidence:** Not allowed.\n\n"
        "## Return\n\nReturn to publication Gate A.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_ci_playbook_records(failures)

    assert any("exactly Origin, Trigger, Mistake, Correction" in failure for failure in failures)


@pytest.mark.parametrize("blank_field", ("Origin", "Trigger", "Mistake", "Correction"))
def test_ci_playbook_rejects_a_blank_required_value(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    blank_field: str,
) -> None:
    values = {
        "Origin": "PR #64",
        "Trigger": "A CI failure.",
        "Mistake": "A concrete mistake.",
        "Correction": "A concrete correction.",
    }
    values[blank_field] = ""
    leaf = tmp_path / "ips-microkernel" / "ci" / "knowledge" / "sample.md"
    leaf.parent.mkdir(parents=True)
    fields = "".join(f"- **{field}:** {value}\n" for field, value in values.items())
    leaf.write_text(
        "# CI Playbook: sample corrections\n\n"
        "## Read when\n\nBefore remote push, read this leaf.\n\n"
        f"## Correction records\n\n### Broken record\n\n{fields}\n"
        "## Return\n\nReturn to publication Gate A.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_ci_playbook_records(failures)

    assert any("required fields must be non-empty" in failure for failure in failures)


def test_gate_a_stage_b_push_and_review_order() -> None:
    publish = (REPOSITORY_ROOT / "ips-microkernel" / "procedures" / "publish.md").read_text(
        encoding="utf-8"
    )
    preflight = (
        REPOSITORY_ROOT / "ips-microkernel" / "ci" / "procedures" / "preflight.md"
    ).read_text(encoding="utf-8")
    assert (
        publish.index("Commit the complete verified candidate tersely without pushing")
        < publish.index("complete publication Gate A")
        < publish.index("Push only the exact Gate-A-checked `HEAD`")
        < publish.index("Require GitHub Actions to target and succeed")
        < publish.index("Complete publication Gate B")
        < publish.index("Dispatch only after Stage B passes")
    )
    assert (
        preflight.index("complete local commit")
        < preflight.index("CI Playbook selector")
        < preflight.index("repair applicable test/proof scripts before remote push")
        < preflight.index("Whenever local `HEAD` changes")
    )
    assert "Never defer CI Playbook reading" in preflight
    assert "Editing only live PR metadata preserves successful exact-head CI" in publish
    assert "without requiring a push or CI run solely to certify" in publish

    follow_up = publish.split("## Follow-up push", 1)[1].split("## Conditional exception", 1)[0]
    assert (
        follow_up.index("Complete Gate A before remote push")
        < follow_up.index("Push the one exact checked correction head")
        < follow_up.index("Immediately read the remote branch and live PR head back")
        < follow_up.index("Treat older CI, verdict, and endpoint evidence as stale")
        < follow_up.index("Require GitHub Actions to succeed for the exact read-back head")
        < follow_up.index("Execute Stage B")
    )


def test_adr_0019_is_superseded_by_0022_with_the_complete_operational_model(
    documentation_checker: ModuleType,
) -> None:
    old_path = Path("ips-microkernel/adr/0018-bound-post-correction-careless-mistake-writeback.md")
    relative_path = Path(
        "ips-microkernel/adr/0019-separate-correction-records-from-pre-review-checks.md"
    )
    successor_path = Path("ips-microkernel/adr/0022-allow-stage-b-after-qualified-no-run.md")
    old_source = (REPOSITORY_ROOT / old_path).read_text(encoding="utf-8")
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    successor = (REPOSITORY_ROOT / successor_path).read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    assert relative_path in documentation_checker.REQUIRED_GOVERNANCE_FILES
    assert successor_path in documentation_checker.REQUIRED_GOVERNANCE_FILES
    assert "- Status: Superseded by ADR-0019" in old_source
    assert "- Status: Superseded" in source
    assert "- Superseded by: ADR-0022" in source
    assert "- Status: Accepted" in successor
    assert "- Supersedes: ADR-0019" in successor
    assert "Make Implementation Prune Stage A an occurrence ledger" in source
    assert "Keep Implementation Prune Stage B as a post-CI pre-review check" in source
    assert "Make the CI Playbook a pre-push correction notebook" in source
    assert "has no Stage A/B or proved/unproved classification" in normalized
    assert "before remote push" in normalized
    assert "Duplicate Mistake and Correction text is deliberate" in normalized
    assert "Stage B problem whose repair is HEAD-neutral" in source
    assert "Separate operational recording from candidate proof" in source


def test_adr_0021_and_0022_are_required_governance_records(
    documentation_checker: ModuleType,
) -> None:
    required = documentation_checker.REQUIRED_GOVERNANCE_FILES

    assert (
        Path("ips-microkernel/adr/0021-govern-human-feedback-model-evaluation-and-promotion.md")
        in required
    )
    assert Path("ips-microkernel/adr/0022-allow-stage-b-after-qualified-no-run.md") in required


@pytest.mark.parametrize(
    "relative_path",
    (
        Path("ips-microkernel/adr/0021-govern-human-feedback-model-evaluation-and-promotion.md"),
        Path("ips-microkernel/adr/0022-allow-stage-b-after-qualified-no-run.md"),
    ),
)
def test_new_required_governance_record_cannot_disappear(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_path: Path,
) -> None:
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_required_governance_files(
        failures,
        (relative_path,),
    )

    assert failures == [f"missing required governance file {relative_path.as_posix()}"]


def test_final_adr_0022_supersession_contract_rejects_each_weakened_boundary(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for relative_path, fragments in documentation_checker.ADR_0022_SUPERSESSION_FRAGMENTS.items():
        source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        normalized = " ".join(source.split())
        final_fragments = documentation_checker.REQUIRED_GOVERNANCE_TEXT[relative_path]
        assert all(fragment in final_fragments for fragment in fragments)
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

        for fragment in fragments:
            assert fragment in normalized
            target.write_text(
                normalized.replace(fragment, "weakened ADR supersession boundary", 1),
                encoding="utf-8",
            )
            failures: list[str] = []

            documentation_checker._validate_required_governance_text(
                failures,
                {relative_path: final_fragments},
            )

            assert failures == [
                f"{relative_path.as_posix()}: missing governance invariant {fragment!r}"
            ]


def test_adr_0016_is_superseded_by_0024_with_one_convergence_adjudicator(
    documentation_checker: ModuleType,
) -> None:
    predecessor_path = Path(
        "ips-microkernel/adr/0016-adjudicate-review-findings-before-correction.md"
    )
    successor_path = Path("ips-microkernel/adr/0024-adjudicate-correction-loop-convergence.md")
    index_path = Path("ips-microkernel/adr/index.md")
    predecessor = (REPOSITORY_ROOT / predecessor_path).read_text(encoding="utf-8")
    successor = (REPOSITORY_ROOT / successor_path).read_text(encoding="utf-8")
    index = (REPOSITORY_ROOT / index_path).read_text(encoding="utf-8")
    accepted, superseded = index.split("## Superseded records", 1)

    assert predecessor_path in documentation_checker.REQUIRED_GOVERNANCE_FILES
    assert successor_path in documentation_checker.REQUIRED_GOVERNANCE_FILES
    assert "- Status: Superseded" in predecessor
    assert "- Superseded by: ADR-0024" in predecessor
    assert "- Status: Accepted" in successor
    assert "- Supersedes: ADR-0016" in successor
    assert "Add a Review Adjudicator runtime role" in predecessor
    assert "No Convergence Adjudicator" not in predecessor
    assert "Preserve one Review Adjudicator role and independent review" in successor
    assert "`continue-correction`" in successor
    assert "`converge`" in successor
    assert "Carry forward ADR-0016's individual classification semantics" in successor
    assert "three holistic lenses" in successor
    assert "they do not prohibit a later aggregate `converge` decision" in successor
    assert "known regression risk" in successor
    assert "not required for ordinary adjudicator convergence" in " ".join(successor.split())
    assert "creates no follow-up Issue" in " ".join(successor.split())
    assert "ADR-0024" in accepted
    assert "ADR-0016" not in accepted
    assert "ADR-0016" in superseded


def test_adr_0024_supersession_contract_rejects_each_weakened_boundary(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for relative_path, fragments in documentation_checker.ADR_0024_SUPERSESSION_FRAGMENTS.items():
        source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        normalized = " ".join(source.split())
        final_fragments = documentation_checker.REQUIRED_GOVERNANCE_TEXT[relative_path]
        assert all(fragment in final_fragments for fragment in fragments)
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

        for fragment in fragments:
            assert fragment in normalized
            target.write_text(
                normalized.replace(fragment, "weakened convergence boundary", 1),
                encoding="utf-8",
            )
            failures: list[str] = []

            documentation_checker._validate_required_governance_text(
                failures,
                {relative_path: final_fragments},
            )

            assert failures == [
                f"{relative_path.as_posix()}: missing governance invariant {fragment!r}"
            ]


def test_adr_0020_authorizes_an_unrestricted_local_focus_scratchpad(
    documentation_checker: ModuleType,
) -> None:
    relative_path = Path("ips-microkernel/adr/0020-authorize-owner-controlled-focus-scratchpad.md")
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    assert relative_path in documentation_checker.REQUIRED_GOVERNANCE_FILES
    assert "- Status: Accepted" in source
    assert "owner-controlled, Git-ignored local workspace" in normalized
    assert "full discretion over everything beneath that directory" in normalized
    assert "has no required trigger, layout, template, naming scheme, size" in normalized
    assert "No tracked template, bootstrap file, or executable is provided" in normalized
    assert "Require focus-end cleanup or reconciliation" in source


@pytest.mark.parametrize(
    ("relative_path", "fragment"),
    (
        (
            Path("ips-microkernel/procedures/implement.md"),
            "Do not read prior Implementation Prune Stage A occurrence files",
        ),
        (
            Path("ips-microkernel/ci/procedures/preflight.md"),
            "Whenever local `HEAD` changes",
        ),
        (
            Path("ips-microkernel/procedures/publish.md"),
            "Editing only live PR metadata preserves successful exact-head CI",
        ),
        (
            Path("ips-microkernel/procedures/publish.md"),
            "Immediately read the remote branch and live PR head back",
        ),
        (
            Path("ips-microkernel/knowledge/behavior.md"),
            "Each rule contains exactly Trigger, HEAD effect, Problem, Detect, "
            "Pass, Repair, and Origins",
        ),
        (
            Path("ips-microkernel/knowledge/behavior.md"),
            "automatically meets the Stage B recording requirement",
        ),
        (
            Path("ips-microkernel/knowledge/behavior.md"),
            "without requiring a push or CI run solely to prove that rule",
        ),
        (
            Path("ips-microkernel/ci/router.md"),
            "fallible duplicate-preserving correction notebook",
        ),
        (
            Path("ips-microkernel/ci/knowledge/selector.md"),
            "Do not read the CI Playbook after remote push",
        ),
        (
            Path("ips-microkernel/adr/0019-separate-correction-records-from-pre-review-checks.md"),
            "Do not scan existing entries for reuse or deduplication",
        ),
    ),
)
def test_operational_record_contract_rejects_a_weakened_boundary(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_path: Path,
    fragment: str,
) -> None:
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    normalized = " ".join(source.split())
    assert fragment in normalized
    destination = tmp_path / relative_path
    destination.parent.mkdir(parents=True)
    destination.write_text(
        normalized.replace(fragment, "weakened boundary"),
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_required_governance_text(
        failures,
        {relative_path: (fragment,)},
    )

    assert failures == [f"{relative_path.as_posix()}: missing governance invariant {fragment!r}"]


def test_review_adjudication_contract_is_complete(
    documentation_checker: ModuleType,
) -> None:
    contract = documentation_checker.REVIEW_ADJUDICATION_FRAGMENTS
    required_text = documentation_checker.REQUIRED_GOVERNANCE_TEXT
    routes = documentation_checker.REQUIRED_ROUTE_LINKS
    roles = documentation_checker.IPS_FILE_ROLES
    adjudication = Path("ips-microkernel/procedures/adjudicate.md")

    assert roles[adjudication] == "procedure"
    assert documentation_checker.CANONICAL_RULE_OWNERS["review-adjudication"] == (adjudication)
    assert adjudication in routes[Path("ips-microkernel/work-router.md")]
    assert adjudication in routes[Path("ips-microkernel/procedures/publish.md")]
    assert Path("ips-microkernel/procedures/correct.md") in routes[adjudication]
    assert Path("ips-microkernel/procedures/merge.md") in routes[adjudication]
    assert adjudication not in routes[Path("ips-microkernel/review/router.md")]
    assert all(
        path in required_text and all(fragment in required_text[path] for fragment in fragments)
        for path, fragments in contract.items()
    )
    assert (
        "The only permitted GitHub write" in required_text[Path("ips-microkernel/review/router.md")]
    )
    review_inspection = (REPOSITORY_ROOT / "ips-microkernel/review/inspect.md").read_text(
        encoding="utf-8"
    )
    assert "Do not request speculative expansion" in review_inspection


@pytest.mark.parametrize(
    ("relative_path", "fragment"),
    (
        (
            Path("ips-microkernel/work-router.md"),
            "`Changes requested` verdict has incomplete finding disposition or "
            "correction-loop decision",
        ),
        (
            Path("ips-microkernel/references/authority.md"),
            "does not silently adjudicate while implementing",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "Do not modify implementation",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "No Convergence Adjudicator",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "applicable ordered chain",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "materially breaks Issue-defined accepted product design at Critical or High "
            "actual impact",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "record the lower actual impact and rationale",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "human discoverability and bounded recoverability, external technical "
            "explanation cost, and material product-quality effect as three holistic lenses",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "Assign exactly one individual disposition",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "assign exactly one aggregate decision",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "even when required corrections, Critical or High reviewer severity",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "append one adjudication checkpoint to the focused Issue",
        ),
        (
            Path("ips-microkernel/procedures/publish.md"),
            "`Changes requested` with incomplete finding disposition",
        ),
        (
            Path("ips-microkernel/procedures/correct.md"),
            "complete exact-head adjudication records `continue-correction`",
        ),
        (
            Path("ips-microkernel/procedures/merge.md"),
            "names every unresolved required correction and known regression risk",
        ),
        (
            Path("ips-microkernel/references/authority.md"),
            "creates no follow-up Issue",
        ),
    ),
)
def test_review_adjudication_rejects_each_weakened_boundary(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_path: Path,
    fragment: str,
) -> None:
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    normalized = " ".join(source.split())
    assert fragment in normalized
    weakened = normalized.replace(fragment, "removed adjudication boundary")
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    target.write_text(weakened, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_required_governance_text(
        failures,
        {relative_path: (fragment,)},
    )

    assert failures == [f"{relative_path.as_posix()}: missing governance invariant {fragment!r}"]


def test_review_adjudication_aggregate_decision_is_guarded_on_both_sides(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    relative_path = Path("ips-microkernel/procedures/adjudicate.md")
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    individual = "Assign exactly one individual disposition"
    aggregate = "After every finding has a disposition, assign exactly one aggregate"
    checkpoint = (
        "Before any implementation mutation or merge, append one adjudication\n   checkpoint"
    )

    target.write_text(source, encoding="utf-8")
    failures: list[str] = []
    documentation_checker._validate_review_adjudication_sequence(failures)
    assert failures == []

    target.write_text(
        source.replace(individual, "individual placeholder", 1)
        .replace(aggregate, individual, 1)
        .replace("individual placeholder", aggregate, 1),
        encoding="utf-8",
    )
    failures = []
    documentation_checker._validate_review_adjudication_sequence(failures)
    assert failures == [
        f"{relative_path.as_posix()}: aggregate correction-loop decision must follow "
        "individual finding disposition"
    ]

    target.write_text(
        source.replace(aggregate, "aggregate placeholder", 1)
        .replace(checkpoint, aggregate, 1)
        .replace("aggregate placeholder", checkpoint, 1),
        encoding="utf-8",
    )
    failures = []
    documentation_checker._validate_review_adjudication_sequence(failures)
    assert failures == [
        f"{relative_path.as_posix()}: aggregate correction-loop decision must precede "
        "the focused-Issue checkpoint"
    ]


def test_knowledge_curation_contract_is_complete(
    documentation_checker: ModuleType,
) -> None:
    contract = documentation_checker.KNOWLEDGE_CURATION_FRAGMENTS
    required_text = documentation_checker.REQUIRED_GOVERNANCE_TEXT
    routes = documentation_checker.REQUIRED_ROUTE_LINKS
    roles = documentation_checker.IPS_FILE_ROLES
    curation = Path("ips-microkernel/procedures/curate-knowledge.md")

    assert roles[curation] == "procedure"
    assert documentation_checker.CANONICAL_RULE_OWNERS["knowledge-curation"] == curation
    assert curation in routes[Path("ips-microkernel/work-router.md")]
    assert curation in routes[Path("ips-microkernel/procedures/publish.md")]
    assert curation in routes[Path("ips-microkernel/procedures/adjudicate.md")]
    assert curation in routes[Path("ips-microkernel/procedures/correct.md")]
    assert curation in routes[Path("ips-microkernel/procedures/merge.md")]
    assert curation in routes[Path("ips-microkernel/procedures/governance-reconcile.md")]
    assert Path("ips-microkernel/selectors/governance-knowledge.md") in routes[curation]
    assert curation not in routes[Path("ips-microkernel/review/router.md")]
    assert curation not in routes[Path("ips-microkernel/review/inspect.md")]
    assert all(
        path in required_text and all(fragment in required_text[path] for fragment in fragments)
        for path, fragments in contract.items()
    )
    assert documentation_checker.KNOWLEDGE_CURATOR_ACTION_FRAGMENTS
    assert documentation_checker.KNOWLEDGE_CURATOR_BOUNDARY_FRAGMENTS


def test_knowledge_curator_actor_boundary_is_structurally_bound(
    documentation_checker: ModuleType,
) -> None:
    failures: list[str] = []

    documentation_checker._validate_knowledge_curator_actor_boundary(failures)

    assert failures == []


def test_knowledge_curator_actor_boundary_rejects_a_removed_actor_row(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    relative_path = documentation_checker.KNOWLEDGE_CURATOR_AUTHORITY_PATH
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    actor_row = next(
        line for line in source.splitlines() if line.startswith("| Knowledge Curator |")
    )
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    target.write_text(source.replace(f"{actor_row}\n", ""), encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_knowledge_curator_actor_boundary(failures)

    assert failures == [
        "ips-microkernel/references/authority.md: Knowledge Curator actor row "
        "expected exactly once, found 0"
    ]


def test_knowledge_curator_actor_boundary_rejects_a_weakened_boundary(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    relative_path = documentation_checker.KNOWLEDGE_CURATOR_AUTHORITY_PATH
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    fragment = documentation_checker.KNOWLEDGE_CURATOR_BOUNDARY_FRAGMENTS[1]
    assert fragment in source
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    target.write_text(
        source.replace(fragment, "may perform any lifecycle action"),
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_knowledge_curator_actor_boundary(failures)

    actor_line = next(
        line_number
        for line_number, line in enumerate(source.splitlines(), start=1)
        if line.startswith("| Knowledge Curator |")
    )
    assert failures == [
        f"ips-microkernel/references/authority.md:{actor_line}: Knowledge Curator "
        f"actor row missing boundary {fragment!r}"
    ]


@pytest.mark.parametrize(
    ("relative_path", "fragment"),
    (
        (
            Path("ips-microkernel/work-router.md"),
            "Stable reusable candidates have complete finding disposition and either "
            "proved required corrections or exact `converge` acceptance",
        ),
        (
            Path("ips-microkernel/references/authority.md"),
            "without routine owner confirmation",
        ),
        (
            Path("ips-microkernel/procedures/curate-knowledge.md"),
            "Do not review, modify implementation or guidance",
        ),
        (
            Path("ips-microkernel/procedures/curate-knowledge.md"),
            "complete disposition for every associated actionable finding, if any",
        ),
        (
            Path("ips-microkernel/procedures/curate-knowledge.md"),
            "successful proof of every required correction or a complete exact-head "
            "`converge` checkpoint",
        ),
        (
            Path("ips-microkernel/procedures/curate-knowledge.md"),
            "A candidate with no associated actionable finding or required correction "
            "remains eligible",
        ),
        (
            Path("ips-microkernel/procedures/curate-knowledge.md"),
            "Critical or High product impact alone never forces promotion",
        ),
        (
            Path("ips-microkernel/procedures/curate-knowledge.md"),
            "before any promotion mutation",
        ),
        (
            Path("ips-microkernel/procedures/curate-knowledge.md"),
            "deterministic resurfacing trigger",
        ),
        (
            Path("ips-microkernel/procedures/curate-knowledge.md"),
            "invalidates older exact-head proof and verdicts",
        ),
        (
            Path("ips-microkernel/procedures/curate-knowledge.md"),
            "final changed head must pass required proof and independent exact-head review",
        ),
        (
            Path("ips-microkernel/procedures/merge.md"),
            "Every `promote-current-pr` checkpoint must be implemented",
        ),
        (
            Path("ips-microkernel/procedures/governance-reconcile.md"),
            "A post-merge candidate cannot use `promote-current-pr`",
        ),
    ),
)
def test_knowledge_curation_rejects_each_weakened_boundary(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_path: Path,
    fragment: str,
) -> None:
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    normalized = " ".join(source.split())
    assert fragment in normalized
    weakened = normalized.replace(fragment, "removed knowledge curation boundary")
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    target.write_text(weakened, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_required_governance_text(
        failures,
        {relative_path: (fragment,)},
    )

    assert failures == [f"{relative_path.as_posix()}: missing governance invariant {fragment!r}"]


def test_knowledge_curation_dispositions_are_complete() -> None:
    procedure = (
        REPOSITORY_ROOT / "ips-microkernel" / "procedures" / "curate-knowledge.md"
    ).read_text(encoding="utf-8")
    dispositions = (
        "`discarded`",
        "`already-represented`",
        "`promote-current-pr`",
        "`promote-follow-up`",
        "`deferred`",
        "`unclassified`",
    )

    disposition_block = procedure[
        procedure.index("7. Assign exactly one disposition") : procedure.index(
            "8. Before implementation"
        )
    ]
    assert all(disposition in disposition_block for disposition in dispositions)


@pytest.mark.parametrize(
    (
        "stable_evidence",
        "associated_finding_disposition_complete",
        "required_correction_proof_complete",
        "expected",
    ),
    (
        (True, None, None, True),
        (True, True, None, True),
        (True, True, True, True),
        (False, None, None, False),
        (True, False, None, False),
        (True, None, False, False),
    ),
)
def test_knowledge_curation_candidate_eligibility_is_conditional(
    documentation_checker: ModuleType,
    stable_evidence: bool,
    associated_finding_disposition_complete: bool | None,
    required_correction_proof_complete: bool | None,
    expected: bool,
) -> None:
    assert (
        documentation_checker._knowledge_curation_candidate_is_eligible(
            stable_evidence=stable_evidence,
            associated_finding_disposition_complete=(associated_finding_disposition_complete),
            required_correction_proof_complete=required_correction_proof_complete,
        )
        is expected
    )


def test_knowledge_curation_disposition_semantics_are_structurally_bound(
    documentation_checker: ModuleType,
) -> None:
    failures: list[str] = []

    documentation_checker._validate_knowledge_curation_disposition_semantics(failures)

    assert failures == []


def test_knowledge_curation_dispositions_reject_collapsed_follow_up_semantics(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    relative_path = documentation_checker.KNOWLEDGE_CURATION_DISPOSITION_PATH
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    follow_up = (
        "`promote-follow-up`: the reusable rule is late, cross-boundary, or too\n"
        "     broad for the current PR;"
    )
    collapsed = (
        "`promote-follow-up`: one bounded causal rule can enter the unmerged\n"
        "     current focused PR;"
    )
    assert follow_up in source
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    target.write_text(source.replace(follow_up, collapsed), encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_knowledge_curation_disposition_semantics(failures)

    assert any(
        "'promote-follow-up' disposition definition missing semantic" in failure
        for failure in failures
    )


def test_knowledge_curation_dispositions_reject_swapped_deferred_semantics(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    relative_path = documentation_checker.KNOWLEDGE_CURATION_DISPOSITION_PATH
    source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
    deferred = "`deferred`: a named recurrence or additional-evidence trigger is required;"
    unclassified = "`unclassified`: no honest canonical target or disposition is available."
    assert deferred in source
    assert unclassified in source
    swapped = (
        source.replace(deferred, "DEFERRED_DISPOSITION_SENTINEL")
        .replace(unclassified, f"`unclassified`: {deferred.split(': ', 1)[1]}")
        .replace(
            "DEFERRED_DISPOSITION_SENTINEL",
            f"`deferred`: {unclassified.split(': ', 1)[1]}",
        )
    )
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True)
    target.write_text(swapped, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_knowledge_curation_disposition_semantics(failures)

    assert any(
        "'deferred' disposition definition missing semantic" in failure for failure in failures
    )
    assert any(
        "'unclassified' disposition definition missing semantic" in failure for failure in failures
    )


def test_governance_knowledge_write_route_is_complete(
    documentation_checker: ModuleType,
) -> None:
    routes = documentation_checker.REQUIRED_ROUTE_LINKS
    required_text = documentation_checker.REQUIRED_GOVERNANCE_TEXT
    reconciliation = Path("ips-microkernel/procedures/governance-reconcile.md")
    curation = Path("ips-microkernel/procedures/curate-knowledge.md")
    selector = Path("ips-microkernel/selectors/governance-knowledge.md")

    assert reconciliation in routes[Path("ips-microkernel/work-router.md")]
    assert reconciliation in routes[Path("ips-microkernel/procedures/reconcile.md")]
    assert curation in routes[Path("ips-microkernel/work-router.md")]
    assert curation in routes[reconciliation]
    assert selector in routes[curation]
    assert set(routes[selector]) == {
        Path("ips-microkernel/references/authority.md"),
        Path("ips-microkernel/references/live-state.md"),
        Path("ips-microkernel/references/local-tools.md"),
        Path("ips-microkernel/references/public-safety.md"),
        Path("ips-microkernel/references/evidence.md"),
        Path("ips-microkernel/procedures/focus.md"),
        Path("ips-microkernel/procedures/implement.md"),
        Path("ips-microkernel/procedures/publish.md"),
        Path("ips-microkernel/procedures/adjudicate.md"),
        Path("ips-microkernel/procedures/curate-knowledge.md"),
        Path("ips-microkernel/procedures/correct.md"),
        Path("ips-microkernel/procedures/merge.md"),
        Path("ips-microkernel/procedures/reconcile.md"),
        Path("ips-microkernel/review/setup.md"),
        Path("ips-microkernel/review/inspect.md"),
        Path("ips-microkernel/review/verdict.md"),
        Path("ips-microkernel/review/cleanup.md"),
        Path("ips-microkernel/ci/router.md"),
        Path("ips-microkernel/adr/index.md"),
        Path("ips-microkernel/delivery/index.md"),
    }

    expected_write_guards = {
        reconciliation: (
            "Governance knowledge reconciliation: no new reusable finding",
            "do not create a recursive empty Issue",
            "every pre-merge atomic candidate",
            "A post-merge candidate cannot use `promote-current-pr`",
        ),
        curation: (
            "ordered candidate queue",
            "For each queued candidate",
            "return to step 3 for the next queued candidate",
            "Only after the queue is exhausted",
            "append one curation checkpoint to the focused Issue",
            "final changed head must pass required proof and independent exact-head review",
        ),
        selector: (
            "not an append-only incident ledger",
            "Select one canonical target",
            "accepted focused governance Issue",
            "independently reviewed follow-up PR",
        ),
        Path("ips-microkernel/review/verdict.md"): (
            "Reusable governance candidate",
            "not permission for the reviewer",
        ),
        Path("ips-microkernel/ci/procedures/failure-triage.md"): (
            "Do not preload CI Playbook history before the concrete correction",
            "Append Origin, Trigger, Mistake, and Correction without scanning",
        ),
        Path("ips-microkernel/ci/procedures/post-merge-reconcile.md"): (
            "checks correction-record completeness",
            "does not prove, deduplicate, promote, or curate CI Playbook entries",
        ),
    }
    for path, fragments in expected_write_guards.items():
        assert all(fragment in required_text[path] for fragment in fragments)


def test_governance_selector_rejects_duplicate_signal_keys(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = (
        REPOSITORY_ROOT / "ips-microkernel" / "selectors" / "governance-knowledge.md"
    ).read_text(encoding="utf-8")
    duplicate = source.replace(
        "| `reconciliation` |",
        "| `issue-evidence` |",
        1,
    )
    selector = tmp_path / "ips-microkernel" / "selectors" / "governance-knowledge.md"
    selector.parent.mkdir(parents=True)
    selector.write_text(duplicate, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_governance_knowledge_selector(failures)

    assert any("signal keys must be unique" in failure for failure in failures)
    assert any("signal 'issue-evidence' must map exactly once" in failure for failure in failures)
    assert any("signal 'reconciliation' must map exactly once" in failure for failure in failures)


def test_governance_selector_rejects_ambiguous_evidence_wording(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = (
        REPOSITORY_ROOT / "ips-microkernel" / "selectors" / "governance-knowledge.md"
    ).read_text(encoding="utf-8")
    ambiguous = source.replace(
        "Post-merge sequencing, main fast-forward, branch deletion, or task-owned cleanup",
        "Issue evidence and completion proof",
        1,
    )
    selector = tmp_path / "ips-microkernel" / "selectors" / "governance-knowledge.md"
    selector.parent.mkdir(parents=True)
    selector.write_text(ambiguous, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_governance_knowledge_selector(failures)

    assert any(
        "signal 'reconciliation' is missing disambiguating text 'Post-merge sequencing'" in failure
        for failure in failures
    )


def test_governance_reconciliation_keeps_processing_multiple_candidates() -> None:
    procedure = (
        REPOSITORY_ROOT / "ips-microkernel" / "procedures" / "curate-knowledge.md"
    ).read_text(encoding="utf-8")

    assert (
        procedure.index("ordered candidate queue")
        < procedure.index("For each queued candidate")
        < procedure.index("return to step 3 for the next queued candidate")
        < procedure.index("Only after the queue is exhausted")
    )


def test_review_verdict_has_one_governance_candidate_field() -> None:
    verdict = (REPOSITORY_ROOT / "ips-microkernel" / "review" / "verdict.md").read_text(
        encoding="utf-8"
    )

    assert verdict.count("### Reusable governance candidate") == 1
    assert (
        verdict.index("### Findings or approval basis")
        < verdict.index("### Reusable governance candidate")
        < verdict.index("### Verification")
    )


def _write_review_candidate_capture_fixture(
    tmp_path: Path,
    overrides: dict[Path, tuple[str, str]],
) -> None:
    relative_paths = (
        Path("ips-microkernel/review/inspect.md"),
        Path("ips-microkernel/review/verdict.md"),
        Path("ips-microkernel/procedures/curate-knowledge.md"),
    )
    for relative_path in relative_paths:
        source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        if relative_path in overrides:
            old, new = overrides[relative_path]
            assert old in source
            source = source.replace(old, new)
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")


@pytest.mark.parametrize(
    ("relative_path", "old", "new", "expected_fragment"),
    [
        (
            Path("ips-microkernel/review/inspect.md"),
            "classify every evidenced reusable process or review candidate",
            "classify one reusable process or review candidate",
            "classify every evidenced reusable process or review candidate",
        ),
        (
            Path("ips-microkernel/review/verdict.md"),
            "one numbered item for every atomic reusable candidate",
            "one numbered item for one reusable candidate",
            "one numbered item for every atomic reusable candidate",
        ),
        (
            Path("ips-microkernel/review/verdict.md"),
            "`none` is permitted only when no reusable candidate was discovered",
            "`none` is always permitted",
            "`none` is permitted only when no reusable candidate was discovered",
        ),
        (
            Path("ips-microkernel/procedures/curate-knowledge.md"),
            "Expand every numbered candidate item from every verdict",
            "Expand the first candidate item from every verdict",
            "Expand every numbered candidate item from every verdict",
        ),
        (
            Path("ips-microkernel/procedures/curate-knowledge.md"),
            "Never stop ingestion after the first verdict item",
            "Stop ingestion after the first verdict item",
            "Never stop ingestion after the first verdict item",
        ),
    ],
)
def test_review_candidate_capture_rejects_lossy_regressions(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_path: Path,
    old: str,
    new: str,
    expected_fragment: str,
) -> None:
    _write_review_candidate_capture_fixture(
        tmp_path,
        {relative_path: (old, new)},
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_review_candidate_capture(failures)

    assert any(expected_fragment in failure for failure in failures)


def test_review_candidate_template_demonstrates_multiple_atomic_items(
    documentation_checker: ModuleType,
) -> None:
    failures: list[str] = []

    documentation_checker._validate_review_candidate_capture(failures)

    assert failures == []


def _write_shallow_review_diff_fixture(
    tmp_path: Path,
    overrides: dict[Path, tuple[str, str]],
) -> None:
    relative_paths = (
        Path("ips-microkernel/review/router.md"),
        Path("ips-microkernel/review/setup.md"),
        Path("ips-microkernel/review/inspect.md"),
    )
    for relative_path in relative_paths:
        source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        if relative_path in overrides:
            old, new = overrides[relative_path]
            assert old in source
            source = source.replace(old, new)
        destination = tmp_path / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")


@pytest.mark.parametrize(
    ("relative_path", "old", "new", "expected_fragment"),
    [
        (
            Path("ips-microkernel/review/router.md"),
            "Expected full base SHA",
            "Base branch name",
            "Expected full base SHA",
        ),
        (
            Path("ips-microkernel/review/setup.md"),
            "git fetch --no-tags --depth 1 origin <expected-base-sha>",
            "git fetch --unshallow origin",
            "git fetch --no-tags --depth 1 origin <expected-base-sha>",
        ),
        (
            Path("ips-microkernel/review/setup.md"),
            "git cat-file -e <expected-base-sha>^{commit}",
            "git log --all",
            "git cat-file -e <expected-base-sha>^{commit}",
        ),
        (
            Path("ips-microkernel/review/inspect.md"),
            "git diff --name-status <expected-base-sha> <expected-head-sha>",
            "git diff --name-status <expected-base-sha>...<expected-head-sha>",
            "git diff --name-status <expected-base-sha> <expected-head-sha>",
        ),
        (
            Path("ips-microkernel/review/inspect.md"),
            "canonical GitHub PR patch and complete paginated file inventory",
            "pull request file count",
            "canonical GitHub PR patch and complete paginated file inventory",
        ),
        (
            Path("ips-microkernel/review/inspect.md"),
            "Require the GitHub and exact endpoint inventories to agree",
            "inspect the GitHub and endpoint inventories separately",
            "Require the GitHub and exact endpoint inventories to agree",
        ),
    ],
)
def test_shallow_review_diff_contract_rejects_incomplete_proof(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_path: Path,
    old: str,
    new: str,
    expected_fragment: str,
) -> None:
    _write_shallow_review_diff_fixture(
        tmp_path,
        {relative_path: (old, new)},
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_shallow_review_diff_contract(failures)

    assert any(expected_fragment in failure for failure in failures)


def test_shallow_review_diff_contract_is_complete(
    documentation_checker: ModuleType,
) -> None:
    failures: list[str] = []

    documentation_checker._validate_shallow_review_diff_contract(failures)

    assert failures == []


def test_review_premortem_contract_is_complete(
    documentation_checker: ModuleType,
) -> None:
    inspect = Path("ips-microkernel/review/inspect.md")
    verdict = Path("ips-microkernel/review/verdict.md")
    contract = documentation_checker.REVIEW_PREMORTEM_FRAGMENTS
    required_text = documentation_checker.REQUIRED_GOVERNANCE_TEXT
    failures: list[str] = []

    assert contract.keys() == {inspect, verdict}
    assert all(
        fragment in required_text[relative_path]
        for relative_path, fragments in contract.items()
        for fragment in fragments
    )

    documentation_checker._validate_review_premortem_sequence(failures)

    assert failures == []


def test_review_premortem_contract_rejects_each_weakened_boundary(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    for relative_path, fragments in documentation_checker.REVIEW_PREMORTEM_FRAGMENTS.items():
        source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
        normalized = " ".join(source.split())
        final_fragments = documentation_checker.REQUIRED_GOVERNANCE_TEXT[relative_path]
        assert all(fragment in final_fragments for fragment in fragments)
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)

        for fragment in fragments:
            assert fragment in normalized
            target.write_text(
                normalized.replace(fragment, "weakened pre-mortem boundary", 1),
                encoding="utf-8",
            )
            failures: list[str] = []

            documentation_checker._validate_required_governance_text(
                failures,
                {relative_path: final_fragments},
            )

            assert failures == [
                f"{relative_path.as_posix()}: missing governance invariant {fragment!r}"
            ]


def _swap_review_sequence_markers(source: str, first: str, second: str) -> str:
    assert first in source
    assert second in source
    assert source.index(first) < source.index(second)
    sentinel = "REVIEW_SEQUENCE_FIRST_MARKER"
    assert sentinel not in source
    return source.replace(first, sentinel, 1).replace(second, first, 1).replace(sentinel, second, 1)


def test_review_premortem_must_precede_verification(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inspect = tmp_path / "ips-microkernel/review/inspect.md"
    verdict = tmp_path / "ips-microkernel/review/verdict.md"
    inspect.parent.mkdir(parents=True)
    source = " ".join(
        (REPOSITORY_ROOT / "ips-microkernel/review/inspect.md").read_text(encoding="utf-8").split()
    )
    inspect.write_text(
        _swap_review_sequence_markers(
            source,
            "Before running verification, conduct a bounded pre-mortem",
            "Run the smallest relevant non-Docker static verification",
        ),
        encoding="utf-8",
    )
    verdict.write_text(
        (REPOSITORY_ROOT / "ips-microkernel/review/verdict.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_review_premortem_sequence(failures)

    assert failures == [
        "ips-microkernel/review/inspect.md: bounded pre-mortem must precede local verification"
    ]


def test_review_premortem_must_follow_scope_and_design_judgment(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inspect = tmp_path / "ips-microkernel/review/inspect.md"
    verdict = tmp_path / "ips-microkernel/review/verdict.md"
    inspect.parent.mkdir(parents=True)
    source = " ".join(
        (REPOSITORY_ROOT / "ips-microkernel/review/inspect.md").read_text(encoding="utf-8").split()
    )
    inspect.write_text(
        _swap_review_sequence_markers(
            source,
            "Judge behavior against focused scope, non-targets, failure model, "
            "acceptance criteria, relevant accepted design, tests, and public safety",
            "Before running verification, conduct a bounded pre-mortem",
        ),
        encoding="utf-8",
    )
    verdict.write_text(
        (REPOSITORY_ROOT / "ips-microkernel/review/verdict.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_review_premortem_sequence(failures)

    assert failures == [
        "ips-microkernel/review/inspect.md: focused-scope and accepted-design "
        "judgment must precede the bounded pre-mortem"
    ]


def test_review_premortem_outcome_must_remain_in_verdict_basis(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inspect = tmp_path / "ips-microkernel/review/inspect.md"
    verdict = tmp_path / "ips-microkernel/review/verdict.md"
    inspect.parent.mkdir(parents=True)
    inspect.write_text(
        "Before running verification, conduct a bounded pre-mortem.\n"
        "Run the smallest relevant non-Docker static verification.\n",
        encoding="utf-8",
    )
    verdict.write_text(
        "### Findings or approval basis\n### Reusable governance candidate\nPre-mortem:\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_review_premortem_sequence(failures)

    assert failures == [
        "ips-microkernel/review/verdict.md: pre-mortem outcome must remain "
        "inside findings or approval basis"
    ]


@pytest.mark.parametrize(
    ("relative_path", "stale_directive"),
    [
        (
            Path("CONTRIBUTING.md"),
            "[delivery specifications](ips-microkernel/delivery/) in numeric order",
        ),
        (
            Path("GIT_AGENTS.md"),
            "Read [the AI collaboration contract](ips-microkernel/work-router.md)",
        ),
        (Path("GIT_AGENTS.md"), "accepted ADRs under"),
        (
            Path("ips-microkernel/work-router.md"),
            "Read [GIT_AGENTS.md] and its required design sources",
        ),
        (
            Path("ips-microkernel/work-router.md"),
            "An independent verdict contains actionable findings and no exact "
            "owner waiver accepts them",
        ),
        (
            Path("ips-microkernel/procedures/publish.md"),
            "Actionable verdict: open [correct](correct.md).",
        ),
        (
            Path("ips-microkernel/procedures/correct.md"),
            "Read this file when an independent exact-head verdict contains actionable findings.",
        ),
        (
            Path("ips-microkernel/review/router.md"),
            "accepted ADRs and accepted delivery specifications in numeric order",
        ),
        (
            Path("ips-microkernel/ci/router.md"),
            "Historical evidence ledger",
        ),
    ],
)
def test_governance_rejects_retired_eager_or_monolithic_routes(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_path: Path,
    stale_directive: str,
) -> None:
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stale_directive, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert f"{relative_path.as_posix()}: contains stale routing {stale_directive!r}" in failures


def test_route_validation_rejects_a_missing_required_link(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = documentation_checker.resolved_local_links

    def without_focus(source: Path) -> set[Path]:
        links = original(source)
        if source == Path("ips-microkernel/work-router.md"):
            links.discard(Path("ips-microkernel/procedures/focus.md"))
        return links

    monkeypatch.setattr(documentation_checker, "resolved_local_links", without_focus)
    failures: list[str] = []

    documentation_checker._validate_routes(failures)

    assert (
        "ips-microkernel/work-router.md: missing required route link "
        "ips-microkernel/procedures/focus.md"
    ) in failures


def test_route_validation_rejects_an_unreachable_guidance_file(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        documentation_checker,
        "REQUIRED_ROUTE_LINKS",
        {
            Path("GIT_AGENTS.md"): (
                Path("AI_GUIDANCE.md"),
                Path("ips-microkernel/work-router.md"),
                Path("ips-microkernel/ci/router.md"),
            )
        },
    )
    failures: list[str] = []

    documentation_checker._validate_routes(failures)

    assert "routed governance file is unreachable: ips-microkernel/procedures/focus.md" in failures


def test_route_validation_rejects_an_undeclared_eager_link(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = documentation_checker.resolved_local_links

    def with_exception_preloaded(source: Path) -> set[Path]:
        links = original(source)
        if source == Path("ips-microkernel/ci/procedures/preflight.md"):
            links.add(Path("ips-microkernel/ci/exceptions/markdown-only.md"))
        return links

    monkeypatch.setattr(
        documentation_checker,
        "resolved_local_links",
        with_exception_preloaded,
    )
    failures: list[str] = []

    documentation_checker._validate_routes(failures)

    assert (
        "ips-microkernel/ci/procedures/preflight.md: contains undeclared route link "
        "ips-microkernel/ci/exceptions/markdown-only.md"
    ) in failures


def test_routing_node_budget_rejects_entrypoint_growth(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "GIT_AGENTS.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(
        documentation_checker,
        "ROUTING_NODE_LINE_BUDGETS",
        {Path("GIT_AGENTS.md"): 2},
    )
    failures: list[str] = []

    documentation_checker._validate_routing_node_budgets(failures)

    assert "GIT_AGENTS.md: routing node has 3 lines, budget is 2" in failures


def test_role_validation_rejects_a_missing_marker(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    guidance = tmp_path / "ips-microkernel"
    guidance.mkdir(parents=True)
    (guidance / "work-router.md").write_text("# Router\n", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_inventory_and_roles(failures)

    assert any(
        failure.startswith(
            "ips-microkernel/work-router.md: expected exactly one role marker "
            "'<!-- ips-role: router -->', found []"
        )
        for failure in failures
    )


def test_role_validation_rejects_a_marker_that_disagrees_with_its_path(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reference = tmp_path / "ips-microkernel" / "references" / "authority.md"
    reference.parent.mkdir(parents=True)
    reference.write_text(
        "<!-- ips-role: procedure -->\n## Read when\n## Return\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_inventory_and_roles(failures)

    assert (
        "ips-microkernel/references/authority.md: declared role 'procedure' "
        "disagrees with path role 'reference'"
    ) in failures


def test_role_validation_rejects_correct_and_conflicting_markers(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reference = tmp_path / "ips-microkernel" / "references" / "authority.md"
    reference.parent.mkdir(parents=True)
    reference.write_text(
        "<!-- ips-role: reference -->\n<!-- ips-role: procedure -->\n## Read when\n## Return\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_inventory_and_roles(failures)

    assert (
        "ips-microkernel/references/authority.md: expected exactly one role marker "
        "'<!-- ips-role: reference -->', found ['reference', 'procedure']"
    ) in failures


def test_role_validation_rejects_a_marker_on_a_design_index(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    index = tmp_path / "ips-microkernel" / "adr" / "index.md"
    index.parent.mkdir(parents=True)
    index.write_text("<!-- ips-role: router -->\n", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_inventory_and_roles(failures)

    assert (
        "ips-microkernel/adr/index.md: iPS role markers are forbidden outside "
        "declared role-bearing paths; found ['router']"
    ) in failures


@pytest.mark.parametrize(
    ("relative_path", "tracked_child"),
    [
        (Path("aios"), None),
        (Path("docs"), None),
        (Path(".github/workflows/CI_PLAYBOOK.md"), None),
        (Path("ips-microkernel/ai"), Path("legacy.md")),
    ],
)
def test_legacy_layout_validation_rejects_a_restored_live_path(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    relative_path: Path,
    tracked_child: Path | None,
) -> None:
    legacy = tmp_path / relative_path
    if tracked_child is None and relative_path.suffix:
        legacy.parent.mkdir(parents=True)
        legacy.write_text("legacy\n", encoding="utf-8")
    else:
        legacy.mkdir(parents=True)
        if tracked_child is not None:
            (legacy / tracked_child).write_text("legacy\n", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_legacy_governance_layout(failures)

    assert f"legacy governance path must not exist: {relative_path.as_posix()}" in failures


@pytest.mark.parametrize(
    "marker",
    (
        "<!-- docforai-role: router -->",
        "<!-- aios-role: router -->",
        "<!-- aios-rule: progressive-disclosure -->",
    ),
)
def test_legacy_layout_validation_rejects_a_retired_marker(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    marker: str,
) -> None:
    entrypoint = tmp_path / "GIT_AGENTS.md"
    entrypoint.write_text(f"{marker}\n", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_legacy_governance_layout(failures)

    assert "GIT_AGENTS.md: contains a legacy DocForAI or AIOS marker" in failures


def test_legacy_layout_validation_rejects_a_retired_marker_on_a_design_index(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    index = tmp_path / "ips-microkernel" / "adr" / "index.md"
    index.parent.mkdir(parents=True)
    index.write_text("<!-- aios-role: router -->\n", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_legacy_governance_layout(failures)

    assert "ips-microkernel/adr/index.md: contains a legacy DocForAI or AIOS marker" in failures


def test_legacy_layout_validation_rejects_a_runtime_readme(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    readme = tmp_path / "ips-microkernel" / "selectors" / "README.md"
    readme.parent.mkdir(parents=True)
    readme.write_text("# Hidden selector\n", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_legacy_governance_layout(failures)

    assert (
        "ips-microkernel/selectors/README.md: runtime README.md must use a role-expressive filename"
    ) in failures


def test_canonical_rule_validation_rejects_duplicate_ownership(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    marker = "<!-- ips-rule: test-rule -->"
    first = tmp_path / "ips-microkernel" / "first.md"
    second = tmp_path / "ips-microkernel" / "second.md"
    first.parent.mkdir(parents=True)
    first.write_text(marker, encoding="utf-8")
    second.write_text(marker, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(
        documentation_checker,
        "CANONICAL_RULE_OWNERS",
        {"test-rule": Path("ips-microkernel/first.md")},
    )
    failures: list[str] = []

    documentation_checker._validate_rule_ownership(failures, [first, second])

    assert any("canonical rule 'test-rule' expected once" in item for item in failures)


def test_ci_failure_knowledge_requires_one_canonical_leaf(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge = tmp_path / "ips-microkernel" / "ci" / "knowledge"
    knowledge.mkdir(parents=True)
    (knowledge / "first.md").write_text("run 123", encoding="utf-8")
    (knowledge / "second.md").write_text("run 123", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(
        documentation_checker,
        "REQUIRED_CI_FAILURE_RUN_IDS",
        ("123",),
    )
    failures: list[str] = []

    documentation_checker._validate_ci_failure_knowledge(failures)

    assert "CI failed run 123 must appear in exactly one knowledge leaf, found 2" in failures


def test_owner_confirmation_stop_exists_only_in_focus(
    documentation_checker: ModuleType,
) -> None:
    governance_paths = [
        REPOSITORY_ROOT / path
        for path in sorted(documentation_checker.PUBLIC_GOVERNANCE_SCAN_FILES)
    ]
    failures: list[str] = []

    documentation_checker._validate_owner_confirmation_boundary(failures, governance_paths)

    assert failures == []


def test_owner_confirmation_validation_rejects_a_reintroduced_gate(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    focus = tmp_path / "ips-microkernel" / "procedures" / "focus.md"
    publish = tmp_path / "ips-microkernel" / "procedures" / "publish.md"
    focus.parent.mkdir(parents=True)
    focus.write_text(
        f"{documentation_checker.OWNER_CONFIRMATION_HEADING}\n",
        encoding="utf-8",
    )
    publish.write_text(
        "Wait for explicit owner direction before merge.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_owner_confirmation_boundary(failures, [focus, publish])

    assert (
        "ips-microkernel/procedures/publish.md: contains forbidden owner direction gate; "
        "standing owner-confirmation gates are reserved for focused-slice selection"
    ) in failures


@pytest.mark.parametrize(
    "content",
    [
        "An owner-approved Markdown-only PR may skip Actions.",
        "The owner authorizes local Docker for the exact task.",
        "The owner explicitly authorizes local Docker for the exact task.",
        "The owner explicitly\nauthorizes local Docker for the exact task.",
    ],
)
def test_owner_confirmation_validation_rejects_legacy_navigation_gates(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    content: str,
) -> None:
    focus = tmp_path / "ips-microkernel" / "procedures" / "focus.md"
    navigation = tmp_path / "scripts" / "README.md"
    focus.parent.mkdir(parents=True)
    navigation.parent.mkdir(parents=True)
    focus.write_text(
        f"{documentation_checker.OWNER_CONFIRMATION_HEADING}\n",
        encoding="utf-8",
    )
    navigation.write_text(content, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_owner_confirmation_boundary(failures, [focus, navigation])

    assert any(
        failure.startswith("scripts/README.md: contains forbidden owner ") for failure in failures
    )


def test_owner_confirmation_validation_rejects_a_second_stop_heading(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    focus = tmp_path / "ips-microkernel" / "procedures" / "focus.md"
    merge = tmp_path / "ips-microkernel" / "procedures" / "merge.md"
    focus.parent.mkdir(parents=True)
    focus.write_text(
        f"{documentation_checker.OWNER_CONFIRMATION_HEADING}\n",
        encoding="utf-8",
    )
    merge.write_text("## Stop\n", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_owner_confirmation_boundary(failures, [focus, merge])

    assert any(
        "owner-confirmation STOP must exist exactly once" in failure
        and "ips-microkernel/procedures/merge.md (## Stop)" in failure
        for failure in failures
    )


def test_markdown_scan_prunes_excluded_directories_before_descending(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_walk(root: Path, *, topdown: bool) -> Iterator[tuple[str, list[str], list[str]]]:
        assert root == tmp_path
        assert topdown is True
        directory_names = [".venv", "ips-microkernel"]
        yield str(root), directory_names, []
        assert directory_names == ["ips-microkernel"]
        yield str(root / "ips-microkernel"), [], ["guide.md"]

    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(documentation_checker.os, "walk", fake_walk)

    assert documentation_checker.iter_markdown_files() == [
        tmp_path / "ips-microkernel" / "guide.md"
    ]


def test_governance_rejects_a_missing_ci_router(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert "missing required governance file ips-microkernel/ci/router.md" in failures


@pytest.mark.parametrize(
    ("content", "expected_label"),
    [
        ("Use X:/private/workspace", "Windows absolute path"),
        ("Read /home/example/private", "POSIX absolute path"),
        ("Read /etc/passwd", "POSIX absolute path"),
        ("Read /tmp/private/workspace", "POSIX absolute path"),
        ("Read /workspace/private", "POSIX absolute path"),
        ("Read /Users/alice/private", "POSIX absolute path"),
        ("Read /Applications/Portfolio.app/Contents", "POSIX absolute path"),
        ("Read /Library/Application Support/private", "POSIX absolute path"),
        ("Read /System/Volumes/Data/private", "POSIX absolute path"),
        ("Read /data/private", "POSIX absolute path"),
        ("Read /app/private", "POSIX absolute path"),
        (r"Read \\server\share\private", "UNC absolute path"),
        ("Open file:///tmp/private", "local file URI"),
        ("Read ~/private", "user-home shorthand path"),
        ("Load .codex/memories/export", "machine-local memory path"),
    ],
)
def test_governance_public_safety_patterns_reject_machine_local_paths(
    documentation_checker: ModuleType,
    content: str,
    expected_label: str,
) -> None:
    pattern = documentation_checker.FORBIDDEN_GOVERNANCE_PATTERNS[expected_label]

    assert pattern.search(content) is not None


@pytest.mark.parametrize(
    ("content", "expected_label"),
    [
        ("-----BEGIN PRIVATE KEY-----", "PEM private key"),
        ("ghp_abcdefghijklmnopqrstuvwxyz123456", "GitHub credential"),
        ("AKIAIOSFODNN7EXAMPLE", "cloud access credential"),
        (
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
            "Bearer credential",
        ),
        ("client_secret=realvalue123456", "assigned credential"),
        ("TOKEN=opaquevalue123456", "assigned credential"),
        (
            "client-internal context: undisclosed production architecture",
            "explicit private context",
        ),
        (
            "client context: undisclosed production architecture",
            "explicit private context",
        ),
    ],
)
def test_governance_public_safety_patterns_reject_sensitive_content(
    documentation_checker: ModuleType,
    content: str,
    expected_label: str,
) -> None:
    pattern = documentation_checker.FORBIDDEN_GOVERNANCE_PATTERNS[expected_label]

    assert pattern.search(content) is not None


@pytest.mark.parametrize(
    "content",
    [
        "https://github.com/Kentaro-Ono-jp/Portfolio/blob/main/ips-microkernel/work-router.md",
        "[Repository guidance](GIT_AGENTS.md)",
        "[AI guidance](ips-microkernel/work-router.md)",
        "[ADR index](../adr/index.md)",
        "Compare Issue/PR/Actions evidence",
        "Protect `/api/v1/documents` and expose `/health`.",
        "Use API_KEY=<redacted> and Authorization: Bearer <token>",
        "TOKEN=${TOKEN} and client context: [redacted]",
        "Exclude credentials, private company context, and client context.",
        "Private context: [redacted]",
        "</details>",
    ],
)
def test_governance_public_safety_patterns_allow_portable_references(
    documentation_checker: ModuleType,
    content: str,
) -> None:
    matches = {
        label
        for label, pattern in documentation_checker.FORBIDDEN_GOVERNANCE_PATTERNS.items()
        if pattern.search(content)
    }

    assert matches == set()


@pytest.mark.parametrize(
    ("content", "expected_label"),
    [
        ("Read /tmp/private/workspace", "POSIX absolute path"),
        ("Read /workspace/private", "POSIX absolute path"),
        ("Read /Users/alice/private", "POSIX absolute path"),
        (r"Read \\server\share\private", "UNC absolute path"),
        ("Open file:///tmp/private", "local file URI"),
        ("Read ~/private", "user-home shorthand path"),
    ],
)
def test_governance_scanner_rejects_nonportable_paths_in_nested_ips_microkernel(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    content: str,
    expected_label: str,
) -> None:
    governance_root = tmp_path / "ips-microkernel"
    nested = governance_root / "ci" / "knowledge"
    nested.mkdir(parents=True)
    leak = nested / "leak.md"
    leak.write_text(content, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert f"ips-microkernel/ci/knowledge/leak.md: contains forbidden {expected_label}" in failures


def test_governance_scanner_covers_routed_indexes_outside_runtime_routes(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    routed_index = tmp_path / "ips-microkernel" / "delivery" / "index.md"
    routed_index.parent.mkdir(parents=True)
    routed_index.write_text("Read X:/private/workspace", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    assert Path("ips-microkernel/delivery/index.md") in (
        documentation_checker.ROUTED_PUBLIC_SURFACE
    )
    assert Path("ips-microkernel/adr/index.md") in documentation_checker.ROUTED_PUBLIC_SURFACE

    documentation_checker._validate_public_governance_surface(failures, [routed_index])

    assert (
        "ips-microkernel/delivery/index.md: contains forbidden Windows absolute path"
    ) in failures


def test_design_selection_surface_includes_index_targets(
    documentation_checker: ModuleType,
) -> None:
    relative_paths = {
        path.relative_to(REPOSITORY_ROOT)
        for path in documentation_checker.design_governance_paths()
    }

    assert Path("ips-microkernel/adr/0005-repository-owned-ai-collaboration.md") in relative_paths
    assert Path("ips-microkernel/adr/0006-consolidate-ai-guidance.md") in relative_paths
    assert Path("ips-microkernel/delivery/0002-second-vertical-slice.md") in relative_paths


def test_governance_failures_rejects_a_wrapped_gate_in_selected_design(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    focus = tmp_path / "ips-microkernel" / "procedures" / "focus.md"
    delivery = tmp_path / "ips-microkernel" / "delivery" / "0002-selected.md"
    focus.parent.mkdir(parents=True)
    delivery.parent.mkdir(parents=True)
    focus.write_text(
        f"{documentation_checker.OWNER_CONFIRMATION_HEADING}\n",
        encoding="utf-8",
    )
    delivery.write_text(
        "The owner explicitly\nauthorizes local Docker for this task.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert (
        "ips-microkernel/delivery/0002-selected.md: contains forbidden owner "
        "authorization gate; standing owner-confirmation gates are reserved for "
        "focused-slice selection"
    ) in failures


def test_governance_failures_rejects_a_macos_path_in_selected_design(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    delivery = tmp_path / "ips-microkernel" / "delivery" / "0002-selected.md"
    delivery.parent.mkdir(parents=True)
    delivery.write_text("Read /Users/alice/private", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert (
        "ips-microkernel/delivery/0002-selected.md: contains forbidden POSIX absolute path"
        in failures
    )


def test_governance_failures_allows_an_api_route_in_selected_design(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    delivery = tmp_path / "ips-microkernel" / "delivery" / "0002-selected.md"
    delivery.parent.mkdir(parents=True)
    delivery.write_text("Call GET /api/v1/documents/{documentId}", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert not any(
        failure.startswith(
            "ips-microkernel/delivery/0002-selected.md: contains forbidden POSIX absolute path"
        )
        for failure in failures
    )


def test_governance_scanner_rejects_nonportable_paths_in_root_guidance(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "GIT_AGENTS.md").write_text("Read X:/private/workspace", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert "GIT_AGENTS.md: contains forbidden Windows absolute path" in failures


@pytest.mark.parametrize(
    ("content", "expected_label"),
    [
        ("password=production-password", "assigned credential"),
        (
            "confidential context: unreleased client migration",
            "explicit private context",
        ),
    ],
)
def test_governance_scanner_rejects_sensitive_content_in_ips_microkernel(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    content: str,
    expected_label: str,
) -> None:
    governance_root = tmp_path / "ips-microkernel"
    governance_root.mkdir(parents=True)
    (governance_root / "work-router.md").write_text(content, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert f"ips-microkernel/work-router.md: contains forbidden {expected_label}" in failures


def test_governance_scanner_rejects_an_extra_ips_runtime_file(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    governance_root = tmp_path / "ips-microkernel"
    governance_root.mkdir(parents=True)
    (governance_root / "EXTRA.md").write_text("safe", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert "iPS Microkernel runtime contains unexpected file EXTRA.md" in failures
