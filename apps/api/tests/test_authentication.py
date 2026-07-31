from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any
from urllib.error import URLError
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.exceptions import PyJWKClientError

import reactorfront_api.authentication as authentication
from reactorfront_api.app import public_problem_response
from reactorfront_api.authentication import (
    AuthenticatedPrincipal,
    AuthenticationFailed,
    AuthorizationDenied,
    BearerRequestAuthorizer,
    Capability,
    JwtAccessTokenValidator,
    OidcProviderMetadata,
    authentication_problem,
    authorization_problem,
    build_access_token_validator,
    load_oidc_provider_metadata,
)
from reactorfront_api.domain import PrincipalKind, PrincipalRecord, PublicProblem
from reactorfront_api.settings import Settings

ISSUER = "https://identity.example.invalid/dex"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
JWKS_URL = f"{ISSUER}/keys"
AUDIENCE = "reactorfront-api"
SUBJECT = "synthetic-reviewer"
CORRELATION_ID = UUID("11111111-1111-4111-8111-111111111111")
NOW = datetime.now(UTC)
PRINCIPAL_ID = UUID("55555555-5555-4555-8555-555555555555")


@dataclass
class StaticSigningKeyClient:
    key: object
    error: Exception | None = None
    calls: int = 0

    def get_signing_key_from_jwt(self, _token: str) -> object:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.key


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        return None

    def read(self, _size: int) -> bytes:
        return self._payload


@dataclass
class FakePrincipalResolver:
    error: Exception | None = None
    calls: list[tuple[str, str]] | None = None
    closed: bool = False

    def resolve_oidc_principal(self, *, issuer: str, subject: str) -> PrincipalRecord:
        if self.calls is None:
            self.calls = []
        self.calls.append((issuer, subject))
        if self.error is not None:
            raise self.error
        return PrincipalRecord(
            principal_id=PRINCIPAL_ID,
            kind=PrincipalKind.OIDC,
            issuer=issuer,
            subject=subject,
            system_key=None,
            created_at=NOW,
        )

    def close(self) -> None:
        self.closed = True


@pytest.fixture(scope="module")
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def validator(
    private_key: rsa.RSAPrivateKey,
    *,
    key_error: Exception | None = None,
) -> JwtAccessTokenValidator:
    return JwtAccessTokenValidator(
        issuer=ISSUER,
        audience=AUDIENCE,
        allowed_algorithm="RS256",
        capability_claim="groups",
        capability_mapping={
            "reactorfront-reviewers": [
                Capability.DOCUMENTS_SUBMIT.value,
                Capability.DOCUMENTS_READ.value,
            ]
        },
        clock_skew_seconds=0,
        signing_key_client=StaticSigningKeyClient(
            private_key.public_key(),
            error=key_error,
        ),
    )


def claims(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "iss": ISSUER,
        "sub": SUBJECT,
        "aud": AUDIENCE,
        "iat": NOW,
        "exp": NOW + timedelta(minutes=5),
        "groups": ["reactorfront-reviewers"],
    }
    values.update(overrides)
    return values


def token(
    private_key: rsa.RSAPrivateKey,
    *,
    claim_overrides: dict[str, Any] | None = None,
    algorithm: str = "RS256",
) -> str:
    key: Any = (
        private_key if algorithm == "RS256" else "synthetic-non-authorizing-test-key-material"
    )
    return jwt.encode(
        claims(**(claim_overrides or {})),
        key,
        algorithm=algorithm,
        headers={"kid": "synthetic-key"},
    )


def test_valid_token_maps_only_configured_capabilities(
    private_key: rsa.RSAPrivateKey,
) -> None:
    access_token = token(
        private_key,
        claim_overrides={"groups": ["reactorfront-reviewers", "ignored-group"]},
    )

    principal = validator(private_key).validate(access_token)

    assert principal == AuthenticatedPrincipal(
        issuer=ISSUER,
        subject=SUBJECT,
        capabilities=frozenset(
            {
                Capability.DOCUMENTS_SUBMIT,
                Capability.DOCUMENTS_READ,
            }
        ),
    )
    JwtAccessTokenValidator.require_capability(
        principal,
        Capability.DOCUMENTS_SUBMIT,
    )
    with pytest.raises(AuthorizationDenied):
        JwtAccessTokenValidator.require_capability(
            principal,
            Capability.REVIEWS_WRITE,
        )


@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"iss": "https://untrusted.example.invalid"},
        {"aud": "another-api"},
        {"aud": [AUDIENCE]},
        {"exp": NOW - timedelta(seconds=1)},
        {"nbf": NOW + timedelta(minutes=1)},
        {"sub": ""},
        {"sub": "s" * 256},
        {"groups": "reactorfront-reviewers"},
    ],
)
def test_invalid_claims_fail_closed(
    private_key: rsa.RSAPrivateKey,
    claim_overrides: dict[str, Any],
) -> None:
    with pytest.raises(AuthenticationFailed):
        validator(private_key).validate(token(private_key, claim_overrides=claim_overrides))


def test_missing_required_claim_and_untrusted_algorithm_fail_closed(
    private_key: rsa.RSAPrivateKey,
) -> None:
    missing_exp = claims()
    del missing_exp["exp"]
    missing_token = jwt.encode(
        missing_exp,
        private_key,
        algorithm="RS256",
        headers={"kid": "synthetic-key"},
    )
    with pytest.raises(AuthenticationFailed):
        validator(private_key).validate(missing_token)

    with pytest.raises(AuthenticationFailed):
        validator(private_key).validate(token(private_key, algorithm="HS256"))


@pytest.mark.parametrize("access_token", ["", "x" * (16 * 1024 + 1), "not-a-jwt"])
def test_invalid_token_shape_fails_closed(
    private_key: rsa.RSAPrivateKey,
    access_token: str,
) -> None:
    with pytest.raises(AuthenticationFailed):
        validator(private_key).validate(access_token)


def test_unknown_signing_key_fails_closed(private_key: rsa.RSAPrivateKey) -> None:
    with pytest.raises(AuthenticationFailed):
        validator(
            private_key,
            key_error=PyJWKClientError("unknown synthetic key"),
        ).validate(token(private_key))


def test_discovery_requires_exact_issuer_https_shape_and_allowed_algorithm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps(
        {
            "issuer": ISSUER,
            "jwks_uri": JWKS_URL,
            "id_token_signing_alg_values_supported": ["RS256"],
        }
    ).encode()
    monkeypatch.setattr(
        authentication,
        "urlopen",
        lambda _request, timeout: FakeResponse(payload),
    )

    metadata = load_oidc_provider_metadata(
        discovery_url=DISCOVERY_URL,
        expected_issuer=ISSUER,
        allowed_algorithm="RS256",
        timeout_seconds=2,
    )

    assert metadata.issuer == ISSUER
    assert metadata.jwks_uri == JWKS_URL
    assert metadata.signing_algorithms == {"RS256"}


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"not-json", id="invalid-json"),
        pytest.param(
            json.dumps({"issuer": "https://wrong.invalid", "jwks_uri": JWKS_URL}).encode(),
            id="wrong-issuer",
        ),
        pytest.param(
            json.dumps(
                {
                    "issuer": ISSUER,
                    "jwks_uri": "file:///tmp/keys",
                    "id_token_signing_alg_values_supported": ["RS256"],
                }
            ).encode(),
            id="unsafe-jwks-uri",
        ),
        pytest.param(b"x" * (64 * 1024 + 1), id="oversized"),
    ],
)
def test_invalid_discovery_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
) -> None:
    monkeypatch.setattr(
        authentication,
        "urlopen",
        lambda _request, timeout: FakeResponse(payload),
    )
    with pytest.raises(AuthenticationFailed):
        load_oidc_provider_metadata(
            discovery_url=DISCOVERY_URL,
            expected_issuer=ISSUER,
            allowed_algorithm="RS256",
            timeout_seconds=2,
        )


def test_unavailable_discovery_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(_request: object, timeout: float) -> object:
        del timeout
        raise URLError("synthetic outage")

    monkeypatch.setattr(authentication, "urlopen", unavailable)
    with pytest.raises(AuthenticationFailed):
        load_oidc_provider_metadata(
            discovery_url=DISCOVERY_URL,
            expected_issuer=ISSUER,
            allowed_algorithm="RS256",
            timeout_seconds=2,
        )


def test_public_authentication_problems_are_sanitized_and_correlated() -> None:
    unauthenticated = public_problem_response(authentication_problem(CORRELATION_ID))
    forbidden = public_problem_response(authorization_problem(CORRELATION_ID))

    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["WWW-Authenticate"] == ('Bearer realm="reactorfront-api"')
    assert unauthenticated.headers["X-Correlation-ID"] == str(CORRELATION_ID)
    assert json.loads(bytes(unauthenticated.body)) == {
        "type": "urn:reactorfront:problem:authentication-required",
        "title": "Authentication required",
        "status": 401,
        "detail": "A valid bearer access token is required.",
        "code": "AUTHENTICATION_REQUIRED",
        "correlationId": str(CORRELATION_ID),
    }
    assert forbidden.status_code == 403
    assert "WWW-Authenticate" not in forbidden.headers


def test_invalid_validator_configuration_is_rejected(
    private_key: rsa.RSAPrivateKey,
) -> None:
    with pytest.raises(ValueError, match="only RS256"):
        JwtAccessTokenValidator(
            issuer=ISSUER,
            audience=AUDIENCE,
            allowed_algorithm="HS256",
            capability_claim="groups",
            capability_mapping={},
            clock_skew_seconds=0,
            signing_key_client=StaticSigningKeyClient(private_key.public_key()),
        )
    with pytest.raises(ValueError, match="unknown capability"):
        JwtAccessTokenValidator(
            issuer=ISSUER,
            audience=AUDIENCE,
            allowed_algorithm="RS256",
            capability_claim="groups",
            capability_mapping={"reviewers": ["unknown"]},
            clock_skew_seconds=0,
            signing_key_client=StaticSigningKeyClient(private_key.public_key()),
        )


def test_validator_factory_uses_the_configured_jwks_backchannel(
    private_key: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}
    key_client = StaticSigningKeyClient(private_key.public_key())

    monkeypatch.setattr(
        authentication,
        "load_oidc_provider_metadata",
        lambda **_kwargs: OidcProviderMetadata(
            issuer=ISSUER,
            jwks_uri=f"{ISSUER}/keys",
            signing_algorithms=frozenset({"RS256"}),
        ),
    )

    def make_key_client(uri: str, **kwargs: object) -> StaticSigningKeyClient:
        observed["uri"] = uri
        observed["kwargs"] = kwargs
        return key_client

    monkeypatch.setattr(authentication, "PyJWKClient", make_key_client)
    settings = Settings(
        oidc_issuer=ISSUER,
        oidc_discovery_url=DISCOVERY_URL,
        oidc_jwks_url="http://identity:5556/dex/keys",
        oidc_audience=AUDIENCE,
    )

    principal = build_access_token_validator(settings).validate(token(private_key))

    assert principal.subject == SUBJECT
    assert observed["uri"] == "http://identity:5556/dex/keys"
    assert observed["kwargs"] == {
        "cache_jwk_set": True,
        "lifespan": 300,
        "cache_keys": False,
        "timeout": 2.0,
    }


def test_validator_factory_rejects_a_mismatched_jwks_backchannel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        authentication,
        "load_oidc_provider_metadata",
        lambda **_kwargs: OidcProviderMetadata(
            issuer=ISSUER,
            jwks_uri=f"{ISSUER}/keys",
            signing_algorithms=frozenset({"RS256"}),
        ),
    )
    settings = Settings(
        oidc_issuer=ISSUER,
        oidc_discovery_url=DISCOVERY_URL,
        oidc_jwks_url="http://identity:5556/unrelated-keys",
        oidc_audience=AUDIENCE,
    )

    with pytest.raises(AuthenticationFailed):
        build_access_token_validator(settings)


def test_request_authorizer_resolves_stable_principal_after_capability_check(
    private_key: rsa.RSAPrivateKey,
) -> None:
    resolver = FakePrincipalResolver()
    authorizer = BearerRequestAuthorizer(
        validator=validator(private_key),
        principal_resolver=resolver,
    )

    principal = authorizer.authorize(
        authorization_header=f"Bearer {token(private_key)}",
        capability=Capability.DOCUMENTS_READ,
        correlation_id=CORRELATION_ID,
    )

    assert principal.principal_id == PRINCIPAL_ID
    assert resolver.calls == [(ISSUER, SUBJECT)]
    authorizer.close()
    assert resolver.closed


@pytest.mark.parametrize(
    "header",
    [None, "", "Basic value", "Bearer", "Bearer  value", "Bearer value extra"],
)
def test_request_authorizer_rejects_missing_or_malformed_bearer_header(
    private_key: rsa.RSAPrivateKey,
    header: str | None,
) -> None:
    authorizer = BearerRequestAuthorizer(
        validator=validator(private_key),
        principal_resolver=FakePrincipalResolver(),
    )

    with pytest.raises(PublicProblem) as captured:
        authorizer.authorize(
            authorization_header=header,
            capability=Capability.DOCUMENTS_READ,
            correlation_id=CORRELATION_ID,
        )

    assert captured.value.status == 401
    assert captured.value.response_headers == {
        "WWW-Authenticate": 'Bearer realm="reactorfront-api"'
    }


def test_request_authorizer_separates_invalid_token_capability_and_dependency(
    private_key: rsa.RSAPrivateKey,
) -> None:
    cases = [
        (
            BearerRequestAuthorizer(
                validator=validator(private_key),
                principal_resolver=FakePrincipalResolver(),
            ),
            "Bearer not-a-jwt",
            401,
        ),
        (
            BearerRequestAuthorizer(
                validator=validator(private_key),
                principal_resolver=FakePrincipalResolver(),
            ),
            f"Bearer {token(private_key, claim_overrides={'groups': []})}",
            403,
        ),
        (
            BearerRequestAuthorizer(
                validator=validator(private_key),
                principal_resolver=FakePrincipalResolver(error=RuntimeError("private")),
            ),
            f"Bearer {token(private_key)}",
            503,
        ),
    ]
    for authorizer, header, expected_status in cases:
        with pytest.raises(PublicProblem) as captured:
            authorizer.authorize(
                authorization_header=header,
                capability=Capability.DOCUMENTS_READ,
                correlation_id=CORRELATION_ID,
            )
        assert captured.value.status == expected_status
        assert "private" not in captured.value.detail
