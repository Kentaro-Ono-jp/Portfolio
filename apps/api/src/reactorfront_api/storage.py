from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
from botocore.config import Config

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

from reactorfront_api.domain import StoredObject


class S3ObjectStorage:
    def __init__(self, *, client: S3Client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def create(
        cls,
        *,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        region: str,
    ) -> S3ObjectStorage:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        return cls(client=client, bucket=bucket)

    def put(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        sha256: str,
    ) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=content,
            ContentLength=len(content),
            ContentType=content_type,
            Metadata={"sha256": sha256},
        )

    def delete(self, *, object_key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=object_key)

    def get(self, *, object_key: str, maximum_bytes: int) -> StoredObject:
        response = self._client.get_object(Bucket=self._bucket, Key=object_key)
        body = response["Body"]
        try:
            content = body.read(maximum_bytes + 1)
        finally:
            body.close()
        if len(content) > maximum_bytes:
            raise ValueError("The stored source exceeds the supported size limit.")

        content_type = response.get("ContentType")
        content_length = response.get("ContentLength")
        metadata = response.get("Metadata") or {}
        if not isinstance(content_type, str) or not isinstance(content_length, int):
            raise ValueError("The stored source metadata is incomplete.")

        stored_sha256 = metadata.get("sha256")
        return StoredObject(
            content=content,
            content_type=content_type,
            size_bytes=content_length,
            sha256=stored_sha256 if isinstance(stored_sha256, str) else None,
        )

    def is_ready(self) -> bool:
        self._client.head_bucket(Bucket=self._bucket)
        return True
