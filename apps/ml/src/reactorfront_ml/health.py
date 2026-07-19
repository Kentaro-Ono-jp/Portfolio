from __future__ import annotations

import argparse

from reactorfront_ml.model import ModelArtifactError
from reactorfront_ml.runtime import build_runtime
from reactorfront_ml.settings import Settings


def is_ready(settings: Settings) -> bool:
    try:
        runtime = build_runtime(settings)
    except (ModelArtifactError, OSError, ValueError):
        return False
    return runtime.storage.is_ready() and runtime.publisher.is_ready()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check ML worker dependencies.")
    parser.add_argument("--check", action="store_true", required=True)
    return parser.parse_args()


def main() -> int:
    parse_args()
    if not is_ready(Settings()):
        print("ML worker readiness failed.")
        return 1
    print("ML worker model, MinIO, and RabbitMQ readiness passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
