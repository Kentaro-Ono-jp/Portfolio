from __future__ import annotations

from unittest.mock import MagicMock, patch

from reactorfront_api.storage import S3ObjectStorage


def test_storage_uses_path_style_s3_and_integrity_metadata() -> None:
    client = MagicMock()
    with patch("reactorfront_api.storage.boto3.client", return_value=client) as create_client:
        storage = S3ObjectStorage.create(
            mode="local",
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

    body = MagicMock()
    body.read.return_value = b"%PDF-test"
    client.get_object.return_value = {
        "Body": body,
        "ContentType": "application/pdf",
        "ContentLength": 9,
        "Metadata": {"sha256": "a" * 64},
    }
    stored = storage.get(object_key="documents/id/source.pdf", maximum_bytes=10)
    assert stored.content == b"%PDF-test"
    assert stored.content_type == "application/pdf"
    assert stored.size_bytes == 9
    assert stored.sha256 == "a" * 64
    body.read.assert_called_once_with(11)
    body.close.assert_called_once_with()

    storage.delete(object_key="documents/id/source.pdf")
    client.delete_object.assert_called_once_with(
        Bucket="portfolio-documents",
        Key="documents/id/source.pdf",
    )
    assert storage.is_ready()
    client.head_bucket.assert_called_once_with(Bucket="portfolio-documents")


def test_storage_uses_standard_credential_chain_in_aws_mode() -> None:
    client = MagicMock()
    with patch("reactorfront_api.storage.boto3.client", return_value=client) as create_client:
        storage = S3ObjectStorage.create(
            mode="aws",
            endpoint_url=None,
            access_key_id=None,
            secret_access_key=None,
            bucket="portfolio-documents",
            region="us-east-1",
        )

    assert storage.is_ready()
    kwargs = create_client.call_args.kwargs
    assert kwargs["region_name"] == "us-east-1"
    assert "endpoint_url" not in kwargs
    assert "aws_access_key_id" not in kwargs
    assert "aws_secret_access_key" not in kwargs
    assert kwargs["config"].s3 is None


def test_storage_rejects_partial_or_mixed_modes() -> None:
    invalid = [
        ("local", "http://minio:9000", "access", None),
        ("local", None, "access", "secret"),
        ("aws", "https://s3.example.invalid", None, None),
        ("aws", None, "access", "secret"),
    ]
    for mode, endpoint, access_key, secret_key in invalid:
        with patch("reactorfront_api.storage.boto3.client") as create_client:
            try:
                S3ObjectStorage.create(
                    mode=mode,  # type: ignore[arg-type]
                    endpoint_url=endpoint,
                    access_key_id=access_key,
                    secret_access_key=secret_key,
                    bucket="portfolio-documents",
                    region="us-east-1",
                )
            except ValueError:
                pass
            else:
                raise AssertionError("unsafe storage configuration was accepted")
            create_client.assert_not_called()
