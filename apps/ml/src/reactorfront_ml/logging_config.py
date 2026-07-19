from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Final

_FIELDS_ATTRIBUTE: Final = "reactorfront_fields"


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        value: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, _FIELDS_ATTRIBUTE, None)
        if isinstance(fields, dict):
            value.update(fields)
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: object,
) -> None:
    logger.log(level, event, extra={_FIELDS_ATTRIBUTE: fields})
