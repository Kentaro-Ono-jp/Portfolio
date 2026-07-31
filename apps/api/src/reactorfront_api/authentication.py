from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import UUID

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError

from reactorfront_api.domain import PrincipalRecord, ProblemCode, PublicProblem
from reactorfront_api.persistence import SqlAlchemyPrincipalRepository, create_database_engine
from reactorfront_api.settings import Settings

MAX_DISCOVERY_DOCUMENT_BYTES = 64 * 1024
MAX_ACCESS_TOKEN_BYTES = 16 * 1024
BEARER_CHALLENGE = 'Bearer realm="reactorfront-api"'


class Capability(StrEnum):
    DOCUMENTS_SUBMIT = "documents:submit"
    DOCUMENTS_READ = "documents:read"
    REVIEWS_WRITE = "reviews:write"
    AUDIT_READ = "audit:read"


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    issuer: str
    subject: str
    capabilities: frozenset[Capability]


@dataclass(frozen=True, slots=True)
class OidcProviderMetadata:
    issuer: str
    jwks_uri: str
    signing_algorithms: frozenset[str]


class AuthenticationFailed(Exception):
    def __init__(self) -> None:
        super().__init__("Access token authentication failed.")


class AuthorizationDenied(Exception):
    def __init__(self) -> None:
        super().__init__("The principal lacks the required capability.")


class SigningKeyClient(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class PrincipalResolver(Protocol):
    def resolve_oidc_principal(self, *, issuer: str, subject: str) -> PrincipalRecord: ...

    def close(self) -> None: ...


class RequestAuthorizer(Protocol):
    def authorize(
        self,
        *,
        authorization_header: str | None,
        capability: Capability,
        correlation_id: UUID,
    ) -> PrincipalRecord: ...

    def close(self) -> None: ...


def _require_http_url(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise AuthenticationFailed
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AuthenticationFailed
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise AuthenticationFailed
    if field == "issuer" and parsed.query:
        raise AuthenticationFailed
    return value


def load_oidc_provider_metadata(
    *,
    discovery_url: str,
    expected_issuer: str,
    allowed_algorithm: str,
    timeout_seconds: float,
) -> OidcProviderMetadata:
    _require_http_url(discovery_url, field="discovery_url")
    _require_http_url(expected_issuer, field="issuer")
    request = Request(
        discovery_url,
        headers={"Accept": "application/json", "User-Agent": "reactorfront-api/0.1"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read(MAX_DISCOVERY_DOCUMENT_BYTES + 1)
        if len(payload) > MAX_DISCOVERY_DOCUMENT_BYTES:
            raise AuthenticationFailed
        document = json.loads(payload)
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AuthenticationFailed from error

    if not isinstance(document, dict):
        raise AuthenticationFailed
    issuer = _require_http_url(document.get("issuer"), field="issuer")
    jwks_uri = _require_http_url(document.get("jwks_uri"), field="jwks_uri")
    algorithms = document.get("id_token_signing_alg_values_supported")
    if (
        issuer != expected_issuer
        or not isinstance(algorithms, list)
        or not all(isinstance(item, str) for item in algorithms)
        or allowed_algorithm not in algorithms
    ):
        raise AuthenticationFailed
    return OidcProviderMetadata(
        issuer=issuer,
        jwks_uri=jwks_uri,
        signing_algorithms=frozenset(algorithms),
    )


def _normalize_capability_mapping(
    raw_mapping: Mapping[str, Sequence[str]],
) -> dict[str, frozenset[Capability]]:
    normalized: dict[str, frozenset[Capability]] = {}
    for external_value, capabilities in raw_mapping.items():
        if not external_value or not isinstance(external_value, str):
            raise ValueError("Capability mapping keys must be non-empty strings.")
        try:
            normalized[external_value] = frozenset(
                Capability(capability) for capability in capabilities
            )
        except ValueError as error:
            raise ValueError("Capability mapping contains an unknown capability.") from error
    return normalized


class JwtAccessTokenValidator:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        allowed_algorithm: str,
        capability_claim: str,
        capability_mapping: Mapping[str, Sequence[str]],
        clock_skew_seconds: int,
        signing_key_client: SigningKeyClient,
    ) -> None:
        if allowed_algorithm != "RS256":
            raise ValueError("The initial boundary permits only RS256.")
        if not audience or not capability_claim:
            raise ValueError("Audience and capability claim must be non-empty.")
        self._issuer = issuer
        self._audience = audience
        self._allowed_algorithm = allowed_algorithm
        self._capability_claim = capability_claim
        self._capability_mapping = _normalize_capability_mapping(capability_mapping)
        self._clock_skew_seconds = clock_skew_seconds
        self._signing_key_client = signing_key_client

    def validate(self, access_token: str) -> AuthenticatedPrincipal:
        if (
            not isinstance(access_token, str)
            or not access_token
            or len(access_token.encode("utf-8")) > MAX_ACCESS_TOKEN_BYTES
        ):
            raise AuthenticationFailed
        try:
            header = jwt.get_unverified_header(access_token)
            if header.get("alg") != self._allowed_algorithm:
                raise AuthenticationFailed
            signing_key = self._signing_key_client.get_signing_key_from_jwt(access_token)
            claims: dict[str, Any] = jwt.decode(
                access_token,
                signing_key,
                algorithms=[self._allowed_algorithm],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._clock_skew_seconds,
                options={
                    "require": ["iss", "sub", "aud", "iat", "exp"],
                    "strict_aud": True,
                },
            )
        except AuthenticationFailed:
            raise
        except (PyJWKClientError, PyJWTError, TypeError, ValueError) as error:
            raise AuthenticationFailed from error

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise AuthenticationFailed
        external_capabilities = claims.get(self._capability_claim, [])
        if not isinstance(external_capabilities, list) or not all(
            isinstance(item, str) for item in external_capabilities
        ):
            raise AuthenticationFailed
        capabilities = frozenset(
            capability
            for external_value in external_capabilities
            for capability in self._capability_mapping.get(external_value, ())
        )
        return AuthenticatedPrincipal(
            issuer=self._issuer,
            subject=subject,
            capabilities=capabilities,
        )

    @staticmethod
    def require_capability(
        principal: AuthenticatedPrincipal,
        capability: Capability,
    ) -> None:
        if capability not in principal.capabilities:
            raise AuthorizationDenied


class BearerRequestAuthorizer:
    def __init__(
        self,
        *,
        validator: JwtAccessTokenValidator,
        principal_resolver: PrincipalResolver,
    ) -> None:
        self._validator = validator
        self._principal_resolver = principal_resolver

    def authorize(
        self,
        *,
        authorization_header: str | None,
        capability: Capability,
        correlation_id: UUID,
    ) -> PrincipalRecord:
        token = self._bearer_token(authorization_header, correlation_id)
        try:
            principal = self._validator.validate(token)
        except AuthenticationFailed as error:
            raise authentication_problem(correlation_id) from error
        try:
            self._validator.require_capability(principal, capability)
        except AuthorizationDenied as error:
            raise authorization_problem(correlation_id) from error
        try:
            return self._principal_resolver.resolve_oidc_principal(
                issuer=principal.issuer,
                subject=principal.subject,
            )
        except Exception as error:
            raise PublicProblem(
                status=503,
                code=ProblemCode.DEPENDENCY_UNAVAILABLE,
                title="Dependency unavailable",
                detail="A required service is temporarily unavailable.",
                correlation_id=correlation_id,
            ) from error

    def close(self) -> None:
        self._principal_resolver.close()

    @staticmethod
    def _bearer_token(
        authorization_header: str | None,
        correlation_id: UUID,
    ) -> str:
        if authorization_header is None or len(authorization_header) > MAX_ACCESS_TOKEN_BYTES + 7:
            raise authentication_problem(correlation_id)
        scheme, separator, token = authorization_header.partition(" ")
        if (
            separator != " "
            or scheme.lower() != "bearer"
            or not token
            or token.strip() != token
            or any(character.isspace() for character in token)
        ):
            raise authentication_problem(correlation_id)
        return token


def build_access_token_validator(settings: Settings) -> JwtAccessTokenValidator:
    metadata = load_oidc_provider_metadata(
        discovery_url=settings.oidc_discovery_url,
        expected_issuer=settings.oidc_issuer,
        allowed_algorithm=settings.oidc_allowed_algorithm,
        timeout_seconds=settings.oidc_http_timeout_seconds,
    )
    configured_jwks_uri = _require_http_url(settings.oidc_jwks_url, field="jwks_uri")
    if urlparse(configured_jwks_uri).path != urlparse(metadata.jwks_uri).path:
        raise AuthenticationFailed
    key_client = PyJWKClient(
        configured_jwks_uri,
        cache_jwk_set=True,
        lifespan=settings.oidc_jwks_cache_seconds,
        cache_keys=False,
        timeout=settings.oidc_http_timeout_seconds,
    )
    return JwtAccessTokenValidator(
        issuer=metadata.issuer,
        audience=settings.oidc_audience,
        allowed_algorithm=settings.oidc_allowed_algorithm,
        capability_claim=settings.oidc_capability_claim,
        capability_mapping=settings.oidc_capability_mapping,
        clock_skew_seconds=settings.oidc_clock_skew_seconds,
        signing_key_client=key_client,
    )


def build_request_authorizer(settings: Settings) -> BearerRequestAuthorizer:
    return BearerRequestAuthorizer(
        validator=build_access_token_validator(settings),
        principal_resolver=SqlAlchemyPrincipalRepository(
            engine=create_database_engine(settings.database_url)
        ),
    )


def authentication_problem(correlation_id: UUID) -> PublicProblem:
    return PublicProblem(
        status=401,
        code=ProblemCode.AUTHENTICATION_REQUIRED,
        title="Authentication required",
        detail="A valid bearer access token is required.",
        correlation_id=correlation_id,
        response_headers={"WWW-Authenticate": BEARER_CHALLENGE},
    )


def authorization_problem(correlation_id: UUID) -> PublicProblem:
    return PublicProblem(
        status=403,
        code=ProblemCode.INSUFFICIENT_CAPABILITY,
        title="Insufficient capability",
        detail="The authenticated principal cannot perform this operation.",
        correlation_id=correlation_id,
    )
