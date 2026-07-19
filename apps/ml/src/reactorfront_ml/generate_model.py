from __future__ import annotations

import argparse
from pathlib import Path

from reactorfront_ml.model import generate_artifact


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the deterministic ML artifact.")
    parser.add_argument("--training-data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--checksum-output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact = generate_artifact(args.training_data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.checksum_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(artifact.content)
    args.checksum_output.write_text(f"{artifact.sha256}\n", encoding="utf-8")
    print(
        f"Generated model sha256={artifact.sha256} "
        f"training_accuracy={artifact.training_accuracy:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
