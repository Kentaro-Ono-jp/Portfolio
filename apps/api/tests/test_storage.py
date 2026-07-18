from __future__ import annotations

from unittest.mock import MagicMock, patch

from reactorfront_api.storage import S3ObjectStorage


def test_storage_uses_path_style_s3_and_integrity_metadata() -> None:
    client = MagicMock()
    with patch("reactorfront_api.storage.boto3.client", return_value=client) as create_client:
        storage = S3ObjectStorage.create(
            endpoint_url="http://minio:9000",
            access_key_id="access",
            secret_access_key="secret",
            bucket="portfolio-documents",
            region="us-east-1",
        )

    create_client.assert_called_once()
    assert create_client.call_args.kwargs["endpoint_url"] == "http://minio:9000"
    assert create_client.call_args.kwargs["config"].s3 == {"addressing_style": "path"}

    storage.put(
        object_key="documents/id/source.pdf",
        content=b"%PDF-test",
        content_type="application/pdf",
        sha256="a" * 64,
    )
    client.put_object.assert_called_once_with(
        Bucket="portfolio-documents",
        Key="documents/id/source.pdf",
        Body=b"%PDF-test",
        ContentLength=9,
        ContentType="application/pdf",
        Metadata={"sha256": "a" * 64},
    )

    storage.delete(object_key="documents/id/source.pdf")
    client.delete_object.assert_called_once_with(
        Bucket="portfolio-documents",
        Key="documents/id/source.pdf",
    )
    assert storage.is_ready()
    client.head_bucket.assert_called_once_with(Bucket="portfolio-documents")
