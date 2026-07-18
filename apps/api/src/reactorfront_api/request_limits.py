from __future__ import annotations

from collections import deque
from collections.abc import Callable
from uuid import UUID, uuid4

from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CORRELATION_HEADER = "X-Correlation-ID"
MULTIPART_ENVELOPE_BYTES = 64 * 1024

LimitResponseFactory = Callable[[UUID], Response]


class UploadRequestBodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        path: str,
        max_body_bytes: int,
        response_factory: LimitResponseFactory,
    ) -> None:
        self._app = app
        self._path = path
        self._max_body_bytes = max_body_bytes
        self._response_factory = response_factory

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._is_limited_request(scope):
            await self._app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        correlation_id = self._correlation_id(headers)
        if self._declared_length_exceeds_limit(headers):
            await self._response_factory(correlation_id)(scope, receive, send)
            return

        buffered_messages: deque[Message] = deque()
        received_bytes = 0
        while True:
            message = await receive()
            buffered_messages.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue
            received_bytes += len(message.get("body", b""))
            if received_bytes > self._max_body_bytes:
                await self._response_factory(correlation_id)(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        async def replay_receive() -> Message:
            if buffered_messages:
                return buffered_messages.popleft()
            return await receive()

        await self._app(scope, replay_receive, send)

    def _is_limited_request(self, scope: Scope) -> bool:
        return (
            scope["type"] == "http"
            and scope.get("method") == "POST"
            and scope.get("path") == self._path
        )

    def _declared_length_exceeds_limit(self, headers: Headers) -> bool:
        value = headers.get("content-length")
        if value is None:
            return False
        try:
            return int(value) > self._max_body_bytes
        except ValueError:
            return False

    @staticmethod
    def _correlation_id(headers: Headers) -> UUID:
        value = headers.get(CORRELATION_HEADER)
        if value is not None:
            try:
                return UUID(value)
            except ValueError:
                pass
        return uuid4()
