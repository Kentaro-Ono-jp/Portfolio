from __future__ import annotations

import importlib.util
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
    ("content", "expected_label"),
    [
        ("Use X:/private/workspace", "Windows absolute path"),
        ("Read /home/example/private", "POSIX absolute path"),
        ("Read /etc/passwd", "POSIX absolute path"),
        ("Read /tmp/private/workspace", "POSIX absolute path"),
        ("Read /workspace/private", "POSIX absolute path"),
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
    "content",
    [
        "https://github.com/Kentaro-Ono-jp/Portfolio/blob/main/docs/ai/README.md",
        "[Repository guidance](GIT_AGENTS.md)",
        "[AI guidance](docs/ai/README.md)",
        "[ADR index](../adr/README.md)",
        "Compare Issue/PR/Actions evidence",
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
        (r"Read \\server\share\private", "UNC absolute path"),
        ("Open file:///tmp/private", "local file URI"),
        ("Read ~/private", "user-home shorthand path"),
    ],
)
def test_governance_scanner_rejects_nonportable_paths_in_ai_docs(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    content: str,
    expected_label: str,
) -> None:
    governance_root = tmp_path / "docs" / "ai"
    governance_root.mkdir(parents=True)
    (governance_root / "leak.md").write_text(content, encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert any(
        failure == f"docs/ai/leak.md: contains forbidden {expected_label}" for failure in failures
    )


def test_governance_scanner_rejects_nonportable_paths_in_root_guidance(
    documentation_checker: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / "GIT_AGENTS.md").write_text("Read X:/private/workspace", encoding="utf-8")
    monkeypatch.setattr(documentation_checker, "REPOSITORY_ROOT", tmp_path)

    failures = documentation_checker.governance_failures()

    assert any(
        failure == "GIT_AGENTS.md: contains forbidden Windows absolute path" for failure in failures
    )
