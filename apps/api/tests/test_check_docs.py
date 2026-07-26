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


def test_progressive_routing_covers_the_complete_guidance_surface(
    documentation_checker: ModuleType,
) -> None:
    routes = documentation_checker.REQUIRED_ROUTE_LINKS
    roles = documentation_checker.DOCFORAI_FILE_ROLES

    assert routes[Path("GIT_AGENTS.md")] == (
        Path("AI_GUIDANCE.md"),
        Path("docs/ai/README.md"),
        Path(".github/workflows/CI_PLAYBOOK.md"),
    )
    assert Path("docs/ai/workflows/focus.md") in routes[Path("docs/ai/README.md")]
    assert Path("docs/ai/workflows/governance-reconcile.md") in routes[Path("docs/ai/README.md")]
    assert Path("docs/ai/ci/markdown-only.md") not in routes[Path("docs/ai/ci/preflight.md")]
    assert Path("docs/ai/ci/knowledge/README.md") in routes[Path("docs/ai/ci/preflight.md")]
    assert Path("docs/ai/knowledge/README.md") not in routes[Path("docs/ai/workflows/implement.md")]
    assert Path("docs/ai/knowledge/README.md") not in routes[Path("docs/ai/review/inspect.md")]
    assert Path("docs/ai/workflows/focus.md") in routes[Path("docs/ai/workflows/correct.md")]
    assert Path("docs/ai/workflows/merge.md") in routes[Path("docs/ai/workflows/correct.md")]
    assert set(roles.values()) == {"router", "procedure", "reference", "knowledge"}


def test_every_canonical_rule_has_one_declared_owner(
    documentation_checker: ModuleType,
) -> None:
    owners = documentation_checker.CANONICAL_RULE_OWNERS

    assert len(owners) == len(set(owners))
    assert len(owners.values()) == len(set(owners.values()))
    assert owners["actor-authority"] == Path("docs/ai/reference/authority.md")
    assert owners["ci-markdown-only-exception"] == Path("docs/ai/ci/markdown-only.md")
    assert owners["governance-knowledge-selection"] == Path("docs/ai/knowledge/README.md")
    assert owners["governance-knowledge-reconciliation"] == Path(
        "docs/ai/workflows/governance-reconcile.md"
    )


def test_governance_knowledge_write_route_is_complete(
    documentation_checker: ModuleType,
) -> None:
    routes = documentation_checker.REQUIRED_ROUTE_LINKS
    required_text = documentation_checker.REQUIRED_GOVERNANCE_TEXT
    reconciliation = Path("docs/ai/workflows/governance-reconcile.md")
    selector = Path("docs/ai/knowledge/README.md")

    assert reconciliation in routes[Path("docs/ai/README.md")]
    assert reconciliation in routes[Path("docs/ai/workflows/reconcile.md")]
    assert selector in routes[reconciliation]
    assert set(routes[selector]) == {
        Path("docs/ai/reference/authority.md"),
        Path("docs/ai/reference/live-state.md"),
        Path("docs/ai/reference/local-tools.md"),
        Path("docs/ai/reference/public-safety.md"),
        Path("docs/ai/reference/evidence.md"),
        Path("docs/ai/workflows/focus.md"),
        Path("docs/ai/workflows/implement.md"),
        Path("docs/ai/workflows/publish.md"),
        Path("docs/ai/workflows/correct.md"),
        Path("docs/ai/workflows/merge.md"),
        Path("docs/ai/workflows/reconcile.md"),
        Path("docs/ai/review/setup.md"),
        Path("docs/ai/review/inspect.md"),
        Path("docs/ai/review/verdict.md"),
        Path("docs/ai/review/cleanup.md"),
        Path(".github/workflows/CI_PLAYBOOK.md"),
        Path("docs/adr/README.md"),
        Path("docs/delivery/README.md"),
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
        Path("docs/ai/review/verdict.md"): (
            "Reusable governance candidate",
            "not permission for the reviewer",
        ),
        Path("docs/ai/ci/failure-triage.md"): (
            "Promote only a new reusable decision rule",
            "Update one canonical knowledge leaf or add one routed leaf",
        ),
        Path("docs/ai/ci/post-merge.md"): (
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
    source = (REPOSITORY_ROOT / "docs" / "ai" / "knowledge" / "README.md").read_text(
        encoding="utf-8"
    )
    duplicate = source.replace(
        "| `reconciliation` |",
        "| `issue-evidence` |",
        1,
    )
    selector = tmp_path / "docs" / "ai" / "knowledge" / "README.md"
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
    source = (REPOSITORY_ROOT / "docs" / "ai" / "knowledge" / "README.md").read_text(
        encoding="utf-8"
    )
    ambiguous = source.replace(
        "Post-merge sequencing, main fast-forward, branch deletion, or task-owned cleanup",
        "Issue evidence and completion proof",
        1,
    )
    selector = tmp_path / "docs" / "ai" / "knowledge" / "README.md"
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
        REPOSITORY_ROOT / "docs" / "ai" / "workflows" / "governance-reconcile.md"
    ).read_text(encoding="utf-8")

    assert (
        procedure.index("ordered candidate queue")
        < procedure.index("For each queued candidate")
        < procedure.index("return to step 4 for the next queued candidate")
        < procedure.index("Only after the queue is exhausted")
    )


def test_review_verdict_has_one_governance_candidate_field() -> None:
    verdict = (REPOSITORY_ROOT / "docs" / "ai" / "review" / "verdict.md").read_text(
        encoding="utf-8"
    )

    assert verdict.count("### Reusable governance candidate") == 1
    assert (
        verdict.index("### Findings or approval basis")
        < verdict.index("### Reusable governance candidate")
        < verdict.index("### Verification")
    )


@pytest.mark.parametrize(
    ("relative_path", "stale_directive"),
    [
        (
            Path("CONTRIBUTING.md"),
            "[delivery specifications](docs/delivery/) in numeric order",
        ),
        (
            Path("GIT_AGENTS.md"),
            "Read [the AI collaboration contract](docs/ai/README.md)",
        ),
        (Path("GIT_AGENTS.md"), "accepted ADRs under"),
        (
            Path("docs/ai/README.md"),
            "Read [GIT_AGENTS.md] and its required design sources",
        ),
        (
            Path("docs/ai/PR_REVIEW.md"),
            "accepted ADRs and accepted delivery specifications in numeric order",
        ),
        (
            Path(".github/workflows/CI_PLAYBOOK.md"),
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
        if source == Path("docs/ai/README.md"):
            links.discard(Path("docs/ai/workflows/focus.md"))
        return links

    monkeypatch.setattr(documentation_checker, "resolved_local_links", without_focus)
    failures: list[str] = []

    documentation_checker._validate_routes(failures)

    assert ("docs/ai/README.md: missing required route link docs/ai/workflows/focus.md") in failures


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
                Path("docs/ai/README.md"),
                Path(".github/workflows/CI_PLAYBOOK.md"),
            )
        },
    )
    failures: list[str] = []

    documentation_checker._validate_routes(failures)

    assert "routed governance file is unreachable: docs/ai/workflows/focus.md" in failures


def test_route_validation_rejects_an_undeclared_eager_link(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = documentation_checker.resolved_local_links

    def with_exception_preloaded(source: Path) -> set[Path]:
        links = original(source)
        if source == Path("docs/ai/ci/preflight.md"):
            links.add(Path("docs/ai/ci/markdown-only.md"))
        return links

    monkeypatch.setattr(
        documentation_checker,
        "resolved_local_links",
        with_exception_preloaded,
    )
    failures: list[str] = []

    documentation_checker._validate_routes(failures)

    assert (
        "docs/ai/ci/preflight.md: contains undeclared route link docs/ai/ci/markdown-only.md"
    ) in failures


def test_router_budget_rejects_entrypoint_growth(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "GIT_AGENTS.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(
        documentation_checker,
        "ROUTER_LINE_BUDGETS",
        {Path("GIT_AGENTS.md"): 2},
    )
    failures: list[str] = []

    documentation_checker._validate_router_budgets(failures)

    assert "GIT_AGENTS.md: router has 3 lines, budget is 2" in failures


def test_role_validation_rejects_a_missing_marker(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    guidance = tmp_path / "docs" / "ai"
    guidance.mkdir(parents=True)
    (guidance / "README.md").write_text("# Router\n", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    documentation_checker._validate_inventory_and_roles(failures)

    assert any(
        failure.startswith(
            "docs/ai/README.md: expected one role marker '<!-- docforai-role: router -->'"
        )
        for failure in failures
    )


def test_canonical_rule_validation_rejects_duplicate_ownership(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    marker = "<!-- docforai-rule: test-rule -->"
    first = tmp_path / "docs" / "ai" / "first.md"
    second = tmp_path / "docs" / "ai" / "second.md"
    first.parent.mkdir(parents=True)
    first.write_text(marker, encoding="utf-8")
    second.write_text(marker, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(
        documentation_checker,
        "CANONICAL_RULE_OWNERS",
        {"test-rule": Path("docs/ai/first.md")},
    )
    failures: list[str] = []

    documentation_checker._validate_rule_ownership(failures, [first, second])

    assert any("canonical rule 'test-rule' expected once" in item for item in failures)


def test_ci_failure_knowledge_requires_one_canonical_leaf(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    knowledge = tmp_path / "docs" / "ai" / "ci" / "knowledge"
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
    focus = tmp_path / "docs" / "ai" / "workflows" / "focus.md"
    publish = tmp_path / "docs" / "ai" / "workflows" / "publish.md"
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
        "docs/ai/workflows/publish.md: contains forbidden owner direction gate; "
        "owner confirmation is reserved for focused-slice selection"
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
    focus = tmp_path / "docs" / "ai" / "workflows" / "focus.md"
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
    focus = tmp_path / "docs" / "ai" / "workflows" / "focus.md"
    merge = tmp_path / "docs" / "ai" / "workflows" / "merge.md"
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
        and "docs/ai/workflows/merge.md (## Stop)" in failure
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
        directory_names = [".venv", "docs"]
        yield str(root), directory_names, []
        assert directory_names == ["docs"]
        yield str(root / "docs"), [], ["guide.md"]

    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setattr(documentation_checker.os, "walk", fake_walk)

    assert documentation_checker.iter_markdown_files() == [tmp_path / "docs" / "guide.md"]


def test_governance_rejects_a_missing_ci_router(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert "missing required governance file .github/workflows/CI_PLAYBOOK.md" in failures


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
        "https://github.com/Kentaro-Ono-jp/Portfolio/blob/main/docs/ai/README.md",
        "[Repository guidance](GIT_AGENTS.md)",
        "[AI guidance](docs/ai/README.md)",
        "[ADR index](../adr/README.md)",
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
def test_governance_scanner_rejects_nonportable_paths_in_nested_ai_docs(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    content: str,
    expected_label: str,
) -> None:
    governance_root = tmp_path / "docs" / "ai"
    nested = governance_root / "ci" / "knowledge"
    nested.mkdir(parents=True)
    leak = nested / "leak.md"
    leak.write_text(content, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert f"docs/ai/ci/knowledge/leak.md: contains forbidden {expected_label}" in failures


def test_governance_scanner_covers_routed_indexes_outside_ai_docs(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    routed_index = tmp_path / "docs" / "delivery" / "README.md"
    routed_index.parent.mkdir(parents=True)
    routed_index.write_text("Read X:/private/workspace", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)
    failures: list[str] = []

    assert Path("docs/delivery/README.md") in (documentation_checker.ROUTED_PUBLIC_SURFACE)
    assert Path("docs/adr/README.md") in documentation_checker.ROUTED_PUBLIC_SURFACE

    documentation_checker._validate_public_governance_surface(failures, [routed_index])

    assert ("docs/delivery/README.md: contains forbidden Windows absolute path") in failures


def test_design_selection_surface_includes_index_targets(
    documentation_checker: ModuleType,
) -> None:
    relative_paths = {
        path.relative_to(REPOSITORY_ROOT)
        for path in documentation_checker.design_governance_paths()
    }

    assert Path("docs/adr/0005-repository-owned-ai-collaboration.md") in relative_paths
    assert Path("docs/adr/0006-consolidate-ai-guidance.md") in relative_paths
    assert Path("docs/delivery/0002-second-vertical-slice.md") in relative_paths


def test_governance_failures_rejects_a_wrapped_gate_in_selected_design(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    focus = tmp_path / "docs" / "ai" / "workflows" / "focus.md"
    delivery = tmp_path / "docs" / "delivery" / "0002-selected.md"
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
        "docs/delivery/0002-selected.md: contains forbidden owner "
        "authorization gate; owner confirmation is reserved for "
        "focused-slice selection"
    ) in failures


def test_governance_failures_rejects_a_macos_path_in_selected_design(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    delivery = tmp_path / "docs" / "delivery" / "0002-selected.md"
    delivery.parent.mkdir(parents=True)
    delivery.write_text("Read /Users/alice/private", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert "docs/delivery/0002-selected.md: contains forbidden POSIX absolute path" in failures


def test_governance_failures_allows_an_api_route_in_selected_design(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    delivery = tmp_path / "docs" / "delivery" / "0002-selected.md"
    delivery.parent.mkdir(parents=True)
    delivery.write_text("Call GET /api/v1/documents/{documentId}", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert not any(
        failure.startswith("docs/delivery/0002-selected.md: contains forbidden POSIX absolute path")
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
def test_governance_scanner_rejects_sensitive_content_in_ai_docs(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    content: str,
    expected_label: str,
) -> None:
    governance_root = tmp_path / "docs" / "ai"
    governance_root.mkdir(parents=True)
    (governance_root / "README.md").write_text(content, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert f"docs/ai/README.md: contains forbidden {expected_label}" in failures


def test_governance_scanner_rejects_an_extra_ai_guidance_file(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    governance_root = tmp_path / "docs" / "ai"
    governance_root.mkdir(parents=True)
    (governance_root / "EXTRA.md").write_text("safe", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert "docs/ai contains unexpected file EXTRA.md" in failures
