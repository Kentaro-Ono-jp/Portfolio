from __future__ import annotations

import importlib.util
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


@pytest.mark.parametrize(
    ("relative_path", "fragment"),
    (
        (
            Path("ips-microkernel/work-router.md"),
            "`Changes requested` verdict contains findings whose disposition is incomplete",
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
            "materially breaks the Issue-defined accepted product design "
            "at Critical or High impact",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "human discoverability and bounded recoverability",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "external technical explanation cost",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "material product-quality effect",
        ),
        (
            Path("ips-microkernel/procedures/adjudicate.md"),
            "Do not use a numeric score",
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
            "only after a complete exact-head adjudication",
        ),
        (
            Path("ips-microkernel/procedures/merge.md"),
            "records zero required corrections",
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


def test_governance_knowledge_write_route_is_complete(
    documentation_checker: ModuleType,
) -> None:
    routes = documentation_checker.REQUIRED_ROUTE_LINKS
    required_text = documentation_checker.REQUIRED_GOVERNANCE_TEXT
    reconciliation = Path("ips-microkernel/procedures/governance-reconcile.md")
    selector = Path("ips-microkernel/selectors/governance-knowledge.md")

    assert reconciliation in routes[Path("ips-microkernel/work-router.md")]
    assert reconciliation in routes[Path("ips-microkernel/procedures/reconcile.md")]
    assert selector in routes[reconciliation]
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
            "accepted focused governance Issue",
            "independently reviewed update",
            "do not create a recursive empty Issue",
            "ordered candidate queue",
            "For each queued candidate",
            "return to step 4 for the next queued candidate",
            "Only after the queue is exhausted",
        ),
        selector: (
            "not an append-only incident ledger",
            "Select one canonical target",
            "accepted focused governance Issue",
            "independently reviewed PR",
        ),
        Path("ips-microkernel/review/verdict.md"): (
            "Reusable governance candidate",
            "not permission for the reviewer",
        ),
        Path("ips-microkernel/ci/procedures/failure-triage.md"): (
            "Promote only a new reusable decision rule",
            "Update one canonical knowledge leaf or add one routed leaf",
        ),
        Path("ips-microkernel/ci/procedures/post-merge-reconcile.md"): (
            "Revise or add one knowledge leaf",
            "focused playbook-update Issue",
            "Publish a knowledge change only through its focused Issue",
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
        REPOSITORY_ROOT / "ips-microkernel" / "procedures" / "governance-reconcile.md"
    ).read_text(encoding="utf-8")

    assert (
        procedure.index("ordered candidate queue")
        < procedure.index("For each queued candidate")
        < procedure.index("return to step 4 for the next queued candidate")
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
        Path("ips-microkernel/procedures/governance-reconcile.md"),
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
            Path("ips-microkernel/procedures/governance-reconcile.md"),
            "Expand every numbered candidate item from every verdict",
            "Expand the first candidate item from every verdict",
            "Expand every numbered candidate item from every verdict",
        ),
        (
            Path("ips-microkernel/procedures/governance-reconcile.md"),
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
