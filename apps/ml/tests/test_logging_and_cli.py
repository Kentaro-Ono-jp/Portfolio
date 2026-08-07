from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import reactorfront_ml.generate_model as generate_model
import reactorfront_ml.generate_promoted_model as generate_promoted_model
import reactorfront_ml.health as health
from reactorfront_ml.logging_config import JsonLogFormatter, configure_logging, log_event


def test_json_formatter_emits_structured_sanitized_fields() -> None:
    record = logging.LogRecord(
        name="reactorfront_ml.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="worker_ready",
        args=(),
        exc_info=None,
    )
    record.reactorfront_fields = {"jobId": "job-1"}

    value = json.loads(JsonLogFormatter().format(record))

    assert value["event"] == "worker_ready"
    assert value["jobId"] == "job-1"
    assert value["level"] == "INFO"
    assert value["timestamp"].endswith("Z")


def test_configure_and_log_event_use_json(capsys: pytest.CaptureFixture[str]) -> None:
    root = logging.getLogger()
    previous_handlers = root.handlers.copy()
    previous_level = root.level
    try:
        configure_logging()
        logger = logging.getLogger("reactorfront_ml.test")

        log_event(logger, logging.WARNING, "worker_warning", failureCode="SAFE_CODE")

        value = json.loads(capsys.readouterr().err)
        assert value["event"] == "worker_warning"
        assert value["failureCode"] == "SAFE_CODE"
    finally:
        root.handlers = previous_handlers
        root.setLevel(previous_level)


def test_generate_model_cli_writes_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    training = Path(__file__).resolve().parents[1] / "data" / "training.json"
    output = tmp_path / "model.json"
    checksum = tmp_path / "model.sha256"
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate-model",
            "--training-data",
            str(training),
            "--output",
            str(output),
            "--checksum-output",
            str(checksum),
        ],
    )

    assert generate_model.main() == 0
    assert output.is_file()
    assert len(checksum.read_text(encoding="utf-8").strip()) == 64


def test_generate_promoted_model_cli_writes_the_manifest_selected_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    evaluation_root = repository_root / "apps" / "ml" / "evaluation"
    output = tmp_path / "promoted.json"
    checksum = tmp_path / "promoted.sha256"
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate-promoted-model",
            "--manifest",
            str(evaluation_root / "promoted-model-v1.json"),
            "--schema",
            str(evaluation_root / "promoted-model-v1.schema.json"),
            "--repository-root",
            str(repository_root),
            "--output",
            str(output),
            "--checksum-output",
            str(checksum),
        ],
    )

    assert generate_promoted_model.main() == 0
    proof = json.loads(capsys.readouterr().out)
    assert proof["modelVersion"] == "document-type-candidate-v1"
    assert proof["artifactSha256"] == checksum.read_text(encoding="utf-8").strip()
    assert output.is_file()


@pytest.mark.parametrize("ready", [True, False])
def test_health_cli_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    ready: bool,
) -> None:
    monkeypatch.setattr("sys.argv", ["health", "--check"])
    monkeypatch.setattr(health, "is_ready", lambda _: ready)

    assert health.main() == (0 if ready else 1)
