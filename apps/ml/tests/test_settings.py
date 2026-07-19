from __future__ import annotations

from reactorfront_ml.settings import Settings


def test_settings_have_no_database_boundary(monkeypatch: object) -> None:
    del monkeypatch
    settings = Settings()

    assert "database" not in " ".join(Settings.model_fields).lower()
    assert settings.rabbitmq_timeout_seconds == 5
    assert settings.s3_bucket == "portfolio-documents"
