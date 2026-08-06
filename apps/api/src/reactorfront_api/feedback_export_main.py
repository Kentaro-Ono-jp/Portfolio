from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from io import BufferedIOBase, TextIOBase
from pathlib import Path

from reactorfront_api.feedback_export import FeedbackExporter, FeedbackExportError
from reactorfront_api.persistence import (
    SqlAlchemyFeedbackExportRepository,
    create_database_engine,
)
from reactorfront_api.settings import get_settings


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export sanitized feedback candidates from API-owned state."
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        required=True,
        help="Canonical reviewed synthetic-corpus inventory JSON.",
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: BufferedIOBase | None = None,
    stderr: TextIOBase | None = None,
) -> int:
    args = parse_args(argv)
    output = stdout if stdout is not None else sys.stdout.buffer
    errors = stderr if stderr is not None else sys.stderr
    repository: SqlAlchemyFeedbackExportRepository | None = None
    rendered: bytes | None = None
    failure_code: str | None = None
    try:
        settings = get_settings()
        engine = create_database_engine(settings.database_url)
        repository = SqlAlchemyFeedbackExportRepository(engine=engine)
        rendered = FeedbackExporter(
            repository=repository,
            inventory_path=args.inventory,
        ).export_bytes()
    except FeedbackExportError as error:
        failure_code = error.code
    except Exception:
        failure_code = "FEEDBACK_EXPORT_FAILED"
    finally:
        if repository is not None:
            try:
                repository.close()
            except Exception:
                if failure_code is None:
                    failure_code = "FEEDBACK_EXPORT_FAILED"
                rendered = None
    if failure_code is not None or rendered is None:
        errors.write(f"feedback export failed: {failure_code or 'FEEDBACK_EXPORT_FAILED'}\n")
        return 1
    try:
        output.write(rendered)
        output.flush()
    except Exception:
        errors.write("feedback export failed: FEEDBACK_OUTPUT_UNAVAILABLE\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
