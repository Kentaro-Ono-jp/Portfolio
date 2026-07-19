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
        ("Read /home/example/private", "user home path"),
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
