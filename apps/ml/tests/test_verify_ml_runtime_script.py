from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def ml_runtime_verifier(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    scripts_directory = REPOSITORY_ROOT / "scripts"
    monkeypatch.syspath_prepend(str(scripts_directory))
    path = scripts_directory / "verify_ml_runtime.py"
    specification = importlib.util.spec_from_file_location(
        "portfolio_verify_ml_runtime",
        path,
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    monkeypatch.setitem(sys.modules, specification.name, module)
    specification.loader.exec_module(module)
    return module


def test_ml_queue_isolation_stops_every_competing_consumer(
    ml_runtime_verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[str, object]] = []
    settings = object()

    monkeypatch.setattr(
        ml_runtime_verifier,
        "compose",
        lambda *arguments: observed.append(("compose", arguments)),
    )
    monkeypatch.setattr(
        ml_runtime_verifier,
        "prepare_queues",
        lambda actual: observed.append(("prepare", actual)),
    )

    ml_runtime_verifier.isolate_ml_result_queue(settings)

    assert observed == [
        ("compose", ("stop", "ml-worker", "api-outbox", "api-events")),
        ("prepare", settings),
        ("compose", ("up", "--detach", "--wait", "api-outbox")),
    ]


def test_promotion_readiness_probe_requires_both_fail_closed_results(
    ml_runtime_verifier: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[object, ...]] = []

    def compose(*arguments: object, capture: bool = False) -> str:
        observed.append(arguments)
        assert capture is True
        return json.dumps(
            {
                "artifactMismatchRejected": True,
                "unreviewedNewestRejected": True,
            }
        )

    monkeypatch.setattr(ml_runtime_verifier, "compose", compose)

    assert ml_runtime_verifier.prove_promotion_readiness_fail_closed() == {
        "artifactMismatchRejected": True,
        "unreviewedNewestRejected": True,
    }
    assert observed[0][:4] == ("exec", "-T", "ml-worker", "python")
