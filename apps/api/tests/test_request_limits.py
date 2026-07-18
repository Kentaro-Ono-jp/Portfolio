from __future__ import annotations

import asyncio
import json
from collections import deque
from uuid import UUID

from starlette.types import Message, Receive, Scope, Send

from reactorfront_api.app import document_too_large_response
from reactorfront_api.request_limits import (
    MULTIPART_ENVELOPE_BYTES,
    UploadRequestBodyLimitMiddleware,
)
from reactorfront_api.service import MAX_DOCUMENT_BYTES

CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")


def test_receive_stream_stops_as_soon_as_upload_request_limit_is_exceeded() -> None:
    chunk = b"x" * (64 * 1024)
    messages: deque[Message] = deque(
        {
            "type": "http.request",
            "body": chunk,
            "more_body": True,
        }
        for _ in range(200)
    )
    receive_calls = 0
    sent: list[Message] = []
    downstream_called = False

    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal downstream_called
        downstream_called = True

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        return messages.popleft()

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/documents",
        "raw_path": b"/api/v1/documents",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"x-correlation-id", str(CORRELATION_ID).encode())],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    middleware = UploadRequestBodyLimitMiddleware(
        downstream,
        path="/api/v1/documents",
        max_body_bytes=MAX_DOCUMENT_BYTES + MULTIPART_ENVELOPE_BYTES,
        response_factory=document_too_large_response,
    )

    asyncio.run(middleware(scope, receive, send))

    response_start = sent[0]
    response_body = sent[1]
    assert response_start["type"] == "http.response.start"
    assert response_start["status"] == 413
    assert dict(response_start["headers"])[b"x-correlation-id"] == str(CORRELATION_ID).encode()
    assert response_body["type"] == "http.response.body"
    assert json.loads(response_body["body"])["code"] == "DOCUMENT_TOO_LARGE"
    assert receive_calls < 200
    assert not downstream_called
