from __future__ import annotations

import argparse
import json
from pathlib import Path

from reactorfront_ml.promotion import load_promoted_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate the exact artifact selected by the reviewed promotion manifest."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--checksum-output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    promoted = load_promoted_model(
        args.manifest,
        args.schema,
        repository_root=args.repository_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.checksum_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(promoted.artifact.content)
    args.checksum_output.write_text(f"{promoted.artifact.sha256}\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "artifactSha256": promoted.artifact.sha256,
                "manifestSha256": promoted.manifest_sha256,
                "modelVersion": promoted.model_version,
                "selectionType": promoted.selection_type,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
