from __future__ import annotations

import argparse
import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_ROOT = REPOSITORY_ROOT / "infra" / "aws" / "bootstrap"
BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
REGION_PATTERN = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+$")
KEY_PATTERN = re.compile(r"^bootstrap/[a-z0-9][a-z0-9/_-]*\.tfstate$")


def validate_backend_inputs(*, bucket: str, region: str, key: str) -> None:
    if not BUCKET_PATTERN.fullmatch(bucket) or ".." in bucket:
        raise ValueError("bucket must be an explicit valid 3-63 character S3 name")
    if not REGION_PATTERN.fullmatch(region):
        raise ValueError("region must be an explicit AWS region identifier")
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError("key must be an explicit bootstrap/...tfstate path")


def backend_files(*, bucket: str, region: str, key: str) -> dict[str, str]:
    validate_backend_inputs(bucket=bucket, region=region, key=key)
    return {
        "backend_override.tf": ('terraform {\n  backend "s3" {}\n}\n'),
        "backend.hcl": (
            f'bucket       = "{bucket}"\n'
            f'key          = "{key}"\n'
            f'region       = "{region}"\n'
            "encrypt      = true\n"
            "use_lockfile = true\n"
        ),
    }


def prepare_backend(*, bucket: str, region: str, key: str) -> tuple[Path, Path]:
    rendered = backend_files(bucket=bucket, region=region, key=key)
    paths: list[Path] = []
    for filename, content in rendered.items():
        path = BOOTSTRAP_ROOT / filename
        path.write_text(content, encoding="utf-8", newline="\n")
        paths.append(path)
    return paths[0], paths[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare ignored partial S3 backend files after the initial local "
            "bootstrap apply or before adopting an existing owner-controlled backend."
        )
    )
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--key", required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        override, config = prepare_backend(
            bucket=arguments.bucket,
            region=arguments.region,
            key=arguments.key,
        )
    except ValueError as error:
        raise SystemExit(f"Refusing backend preparation: {error}") from error
    print(f"Prepared {override.relative_to(REPOSITORY_ROOT).as_posix()}")
    print(f"Prepared {config.relative_to(REPOSITORY_ROOT).as_posix()}")
    print("Next: terraform init -migrate-state -backend-config=backend.hcl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
