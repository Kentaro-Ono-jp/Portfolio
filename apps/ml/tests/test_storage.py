from __future__ import annotations

from typing import cast

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from mypy_boto3_s3 import S3Client

import reactorfront_ml.storage as storage_module
from reactorfront_ml.domain import (
    PermanentProcessingError,
    ProcessingFailureCode,
    TransientProcessingError,
)
from reactorfront_ml.storage import S3SourceStorage


class FakeBody:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read(self) -> bytes:
        return self._content


class FakeClient:
    def __init__(self) -> None:
        self.response: object = {"Body": FakeBody(b"pdf")}
        self.error: Exception | None = None
        self.head_error: Exception | None = None

    def get_object(self, **_: object) -> object:
        if self.error is not None:
            raise self.error
        return self.response

    def head_bucket(self, **_: object) -> None:
        if self.head_error is not None:
            raise self.head_error


def subject(client: FakeClient) -> S3SourceStorage:
    return S3SourceStorage(client=cast(S3Client, client), bucket="documents")


def client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "private"}}, "GetObject")


def test_get_reads_source_bytes() -> None:
    assert subject(FakeClient()).get(object_key="source.pdf") == b"pdf"


def test_missing_object_is_permanent() -> None:
    client = FakeClient()
    client.error = client_error("NoSuchKey")

    with pytest.raises(PermanentProcessingError) as raised:
        subject(client).get(object_key="missing.pdf")

    assert raised.value.code is ProcessingFailureCode.SOURCE_OBJECT_NOT_FOUND
    assert raised.value.__suppress_context__ is True


def test_other_client_error_is_transient() -> None:
    client = FakeClient()
    client.error = client_error("SlowDown")

    with pytest.raises(TransientProcessingError) as raised:
        subject(client).get(object_key="source.pdf")

    assert raised.value.code is ProcessingFailureCode.SOURCE_UNAVAILABLE
    assert raised.value.__suppress_context__ is True


def test_transport_error_is_transient() -> None:
    client = FakeClient()
    client.error = EndpointConnectionError(endpoint_url="http://minio:9000")

    with pytest.raises(TransientProcessingError):
        subject(client).get(object_key="source.pdf")


def test_readiness_is_false_on_dependency_error() -> None:
    client = FakeClient()
    assert subject(client).is_ready()
    client.head_error = client_error("ServiceUnavailable")
    assert not subject(client).is_ready()


def test_create_configures_bounded_path_style_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    observed: dict[str, object] = {}

    def create_client(service: str, **values: object) -> object:
        observed["service"] = service
        observed.update(values)
        return client

    monkeypatch.setattr(storage_module.boto3, "client", create_client)

    created = S3SourceStorage.create(
        endpoint_url="http://minio:9000",
        access_key_id="access",
        secret_access_key="secret",
        bucket="documents",
        region="us-east-1",
    )

    assert created.get(object_key="source.pdf") == b"pdf"
    assert observed["service"] == "s3"
    assert observed["endpoint_url"] == "http://minio:9000"


def test_non_bytes_body_is_transient() -> None:
    client = FakeClient()
    client.response = {"Body": FakeBody(cast(bytes, "not-bytes"))}

    with pytest.raises(TransientProcessingError):
        subject(client).get(object_key="source.pdf")
