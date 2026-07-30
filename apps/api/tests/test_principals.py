from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID

import pytest

import reactorfront_api.persistence as persistence
from reactorfront_api.domain import PrincipalKind
from reactorfront_api.persistence import PrincipalRow, SqlAlchemyPrincipalRepository

PRINCIPAL_ID = UUID("55555555-5555-4555-8555-555555555555")
NOW = datetime(2026, 7, 31, 1, 0, tzinfo=UTC)
ISSUER = "https://identity.example.invalid/dex"
SUBJECT = "synthetic-reviewer"


@dataclass
class FakePrincipalSession:
    scalar_values: list[PrincipalRow | None]
    statements: list[object] = field(default_factory=list)

    def __enter__(self) -> FakePrincipalSession:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        return None

    def begin(self) -> FakePrincipalSession:
        return self

    def scalar(self, statement: object) -> PrincipalRow | None:
        self.statements.append(statement)
        return self.scalar_values.pop(0)


@dataclass
class FakeEngine:
    disposed: bool = False

    def dispose(self) -> None:
        self.disposed = True


def oidc_row() -> PrincipalRow:
    return PrincipalRow(
        id=PRINCIPAL_ID,
        kind=PrincipalKind.OIDC.value,
        issuer=ISSUER,
        subject=SUBJECT,
        system_key=None,
        created_at=NOW,
    )


@pytest.mark.parametrize(
    "scalar_values",
    [
        [oidc_row()],
        [None, oidc_row()],
    ],
)
def test_oidc_principal_resolution_returns_inserted_or_concurrent_identity(
    monkeypatch: pytest.MonkeyPatch,
    scalar_values: list[PrincipalRow | None],
) -> None:
    session = FakePrincipalSession(scalar_values=scalar_values)
    monkeypatch.setattr(persistence, "Session", lambda _engine: session)
    repository = SqlAlchemyPrincipalRepository(engine=object())  # type: ignore[arg-type]

    record = repository.resolve_oidc_principal(issuer=ISSUER, subject=SUBJECT)

    assert record.principal_id == PRINCIPAL_ID
    assert record.kind is PrincipalKind.OIDC
    assert record.issuer == ISSUER
    assert record.subject == SUBJECT
    assert record.system_key is None
    assert len(session.statements) in {1, 2}


def test_oidc_principal_resolution_rejects_invalid_or_missing_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SqlAlchemyPrincipalRepository(engine=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        repository.resolve_oidc_principal(issuer="", subject=SUBJECT)
    with pytest.raises(ValueError):
        repository.resolve_oidc_principal(issuer=ISSUER, subject="")

    session = FakePrincipalSession(scalar_values=[None, None])
    monkeypatch.setattr(persistence, "Session", lambda _engine: session)
    with pytest.raises(RuntimeError, match="could not be resolved"):
        repository.resolve_oidc_principal(issuer=ISSUER, subject=SUBJECT)


def test_principal_repository_closes_its_engine() -> None:
    engine = FakeEngine()
    repository = SqlAlchemyPrincipalRepository(engine=engine)  # type: ignore[arg-type]

    repository.close()

    assert engine.disposed
