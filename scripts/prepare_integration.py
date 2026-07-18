from __future__ import annotations

import boto3
from botocore.config import Config

from reactorfront_api.settings import get_settings


def main() -> None:
    settings = get_settings()
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    existing_buckets = {
        bucket["Name"] for bucket in client.list_buckets().get("Buckets", [])
    }
    if settings.s3_bucket not in existing_buckets:
        client.create_bucket(Bucket=settings.s3_bucket)
        print(f"Created integration bucket: {settings.s3_bucket}")
    else:
        print(f"Integration bucket already exists: {settings.s3_bucket}")


if __name__ == "__main__":
    main()
