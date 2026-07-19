from __future__ import annotations

from dataclasses import dataclass, field

from reactorfront_ml.domain import ClassificationResult, ResultPublishError


@dataclass
class FakeStorage:
    content: bytes = b""
    error: Exception | None = None
    ready: bool = True
    requested_keys: list[str] = field(default_factory=list)

    def get(self, *, object_key: str) -> bytes:
        self.requested_keys.append(object_key)
        if self.error is not None:
            raise self.error
        return self.content

    def is_ready(self) -> bool:
        return self.ready


@dataclass
class FakeClassifier:
    result: ClassificationResult
    checksum: str = "a" * 64
    error: Exception | None = None
    texts: list[str] = field(default_factory=list)

    def classify(self, text: str) -> ClassificationResult:
        self.texts.append(text)
        if self.error is not None:
            raise self.error
        return self.result


@dataclass
class FakeValidator:
    validated: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def validate(self, *, event_type: str, payload: dict[str, object]) -> None:
        self.validated.append((event_type, payload))


@dataclass
class FakePublisher:
    error: ResultPublishError | None = None
    ready: bool = True
    published: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def publish(self, *, event_type: str, payload: dict[str, object]) -> None:
        if self.error is not None:
            raise self.error
        self.published.append((event_type, payload))

    def is_ready(self) -> bool:
        return self.ready
