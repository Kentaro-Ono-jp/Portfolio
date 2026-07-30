from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import textwrap
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx2 as httpx
from sqlalchemy import create_engine, text

from reactorfront_api.authentication import (
    AuthenticatedPrincipal,
    AuthenticationFailed,
    Capability,
    JwtAccessTokenValidator,
    build_access_token_validator,
)
from reactorfront_api.persistence import (
    LEGACY_SYSTEM_PRINCIPAL_ID,
    SqlAlchemyPrincipalRepository,
)
from reactorfront_api.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIRECTORY = REPOSITORY_ROOT / "artifacts" / "verification"
COMPOSE_PROJECT_NAME = "reactorfront-portfolio"
CLIENT_ID = "reactorfront-api"
REDIRECT_URI = "http://127.0.0.1:5557/callback"
SYNTHETIC_EMAIL = "reviewer@synthetic.invalid"
SYNTHETIC_PASSWORD = "password"
STATE = "reactorfront-synthetic-state"
NONCE = "reactorfront-synthetic-nonce"
VERIFIER = "reactorfront-synthetic-pkce-verifier-000000000000000000000000"


class FormActionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "form" or self.action is not None:
            return
        attributes = dict(attrs)
        self.action = attributes.get("action")


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _redirect_location(response: httpx.Response) -> str | None:
    if not response.is_redirect:
        return None
    location = response.headers.get("location")
    if location is None:
        raise RuntimeError("OIDC redirect omitted its location.")
    return urljoin(str(response.url), location)


def obtain_access_token(settings: Settings) -> tuple[str, dict[str, object]]:
    discovery = httpx.get(settings.oidc_discovery_url, timeout=5)
    discovery.raise_for_status()
    metadata = discovery.json()
    if metadata.get("issuer") != settings.oidc_issuer:
        raise RuntimeError("OIDC discovery returned an unexpected issuer.")
    authorization_endpoint = metadata.get("authorization_endpoint")
    token_endpoint = metadata.get("token_endpoint")
    if not isinstance(authorization_endpoint, str) or not isinstance(
        token_endpoint, str
    ):
        raise RuntimeError("OIDC discovery omitted required endpoints.")

    with httpx.Client(follow_redirects=False, timeout=5) as client:
        response = client.get(
            authorization_endpoint,
            params={
                "client_id": CLIENT_ID,
                "redirect_uri": REDIRECT_URI,
                "response_type": "code",
                "scope": "openid groups",
                "state": STATE,
                "nonce": NONCE,
                "code_challenge": pkce_challenge(VERIFIER),
                "code_challenge_method": "S256",
            },
        )
        for _ in range(5):
            location = _redirect_location(response)
            if location is None:
                break
            if location.startswith(REDIRECT_URI):
                raise RuntimeError("OIDC flow bypassed the synthetic login boundary.")
            response = client.get(location)
        if response.status_code != 200:
            raise RuntimeError("OIDC synthetic login form was unavailable.")

        parser = FormActionParser()
        parser.feed(response.text)
        if parser.action is None:
            raise RuntimeError("OIDC synthetic login form omitted its action.")
        response = client.post(
            urljoin(str(response.url), parser.action),
            content=urlencode(
                {
                    "login": SYNTHETIC_EMAIL,
                    "password": SYNTHETIC_PASSWORD,
                }
            ),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        callback: str | None = None
        for _ in range(5):
            location = _redirect_location(response)
            if location is None:
                break
            if location.startswith(REDIRECT_URI):
                callback = location
                break
            response = client.get(location)
        if callback is None:
            raise RuntimeError("OIDC authorization code callback was not produced.")

        query = parse_qs(urlparse(callback).query)
        if query.get("state") != [STATE] or len(query.get("code", [])) != 1:
            raise RuntimeError("OIDC callback state or authorization code was invalid.")
        token_response = client.post(
            token_endpoint,
            auth=(CLIENT_ID, ""),
            data={
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
                "code": query["code"][0],
                "code_verifier": VERIFIER,
            },
        )
        token_response.raise_for_status()
        token_payload = token_response.json()

    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("OIDC token response omitted the access token.")
    public_metadata = {
        "tokenType": token_payload.get("token_type"),
        "expiresIn": token_payload.get("expires_in"),
        "authorizationCodePkce": True,
    }
    return access_token, public_metadata


def assert_token_absent_from_persistence(database_url: str, access_token: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            for table_name in (
                "principals",
                "documents",
                "processing_jobs",
                "outbox_events",
                "result_event_receipts",
            ):
                found = connection.execute(
                    text(
                        f"SELECT EXISTS (SELECT 1 FROM {table_name} "
                        f"WHERE strpos(row_to_json({table_name})::text, :token) > 0)"
                    ),
                    {"token": access_token},
                ).scalar_one()
                if found:
                    raise RuntimeError(
                        f"Access-token material reached {table_name} persistence."
                    )
    finally:
        engine.dispose()


def assert_token_absent_from_logs_and_evidence(access_token: str) -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            COMPOSE_PROJECT_NAME,
            "logs",
            "--no-color",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    token_bytes = access_token.encode()
    if token_bytes in result.stdout:
        raise RuntimeError("Access-token material reached Compose logs.")
    if ARTIFACT_DIRECTORY.exists():
        for path in ARTIFACT_DIRECTORY.rglob("*"):
            if path.is_file() and token_bytes in path.read_bytes():
                raise RuntimeError(
                    "Access-token material reached verification evidence."
                )


def delete_synthetic_principal(
    database_url: str,
    *,
    issuer: str,
    subject: str,
) -> None:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            result = connection.execute(
                text(
                    "DELETE FROM principals "
                    "WHERE kind = 'oidc' AND issuer = :issuer AND subject = :subject"
                ),
                {"issuer": issuer, "subject": subject},
            )
            if result.rowcount not in {0, 1}:
                raise RuntimeError(
                    "Synthetic principal cleanup affected an unexpected row count."
                )
    finally:
        engine.dispose()


def validate_inside_api_container(access_token: str) -> dict[str, object]:
    probe = textwrap.dedent(
        """
        import json
        import sys

        from sqlalchemy import create_engine

        from reactorfront_api.authentication import build_access_token_validator
        from reactorfront_api.persistence import SqlAlchemyPrincipalRepository
        from reactorfront_api.settings import Settings

        settings = Settings()
        token = sys.stdin.read(16385)
        principal = build_access_token_validator(settings).validate(token)
        repository = SqlAlchemyPrincipalRepository(
            engine=create_engine(settings.database_url)
        )
        try:
            record = repository.resolve_oidc_principal(
                issuer=principal.issuer,
                subject=principal.subject,
            )
        finally:
            repository.close()
        print(json.dumps({
            "principalId": str(record.principal_id),
            "issuer": principal.issuer,
            "subject": principal.subject,
            "capabilities": sorted(item.value for item in principal.capabilities),
        }))
        """
    )
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            COMPOSE_PROJECT_NAME,
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            probe,
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        input=access_token.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "The API-container identity proof was not valid JSON."
        ) from error
    if not isinstance(payload, dict):
        raise RuntimeError("The API-container identity proof was not an object.")
    return payload


def exercise_identity_boundary(
    *,
    settings: Settings,
    access_token: str,
    public_metadata: dict[str, object],
    validator: JwtAccessTokenValidator,
    principal: AuthenticatedPrincipal,
) -> dict[str, object]:
    container_proof = validate_inside_api_container(access_token)

    repository = SqlAlchemyPrincipalRepository(
        engine=create_engine(settings.database_url)
    )
    try:
        first = repository.resolve_oidc_principal(
            issuer=principal.issuer,
            subject=principal.subject,
        )
        repeated = repository.resolve_oidc_principal(
            issuer=principal.issuer,
            subject=principal.subject,
        )
        if (
            first.principal_id != repeated.principal_id
            or first.principal_id == LEGACY_SYSTEM_PRINCIPAL_ID
            or container_proof.get("principalId") != str(first.principal_id)
            or container_proof.get("issuer") != principal.issuer
            or container_proof.get("subject") != principal.subject
            or container_proof.get("capabilities")
            != sorted(capability.value for capability in principal.capabilities)
        ):
            raise RuntimeError(
                "OIDC principal resolution was unstable across the API container boundary."
            )
    finally:
        repository.close()

    token_parts = access_token.split(".")
    if len(token_parts) != 3 or not token_parts[2]:
        raise RuntimeError("The OAuth access token is not a signed JWT.")
    token_parts[2] = ("a" if token_parts[2][0] != "a" else "b") + token_parts[2][1:]
    tampered = ".".join(token_parts)
    try:
        validator.validate(tampered)
    except AuthenticationFailed:
        pass
    else:
        raise RuntimeError("A token with an invalid signature was accepted.")

    assert_token_absent_from_persistence(settings.database_url, access_token)
    assert_token_absent_from_logs_and_evidence(access_token)
    evidence = {
        **public_metadata,
        "issuer": principal.issuer,
        "subject": principal.subject,
        "capabilities": sorted(
            capability.value for capability in principal.capabilities
        ),
        "stablePrincipal": True,
        "distinctLegacyPrincipal": True,
        "tamperedSignatureRejected": True,
        "tokenPersisted": False,
        "tokenLogged": False,
        "tokenInEvidence": False,
    }
    return evidence


def main() -> int:
    settings = Settings()
    access_token, public_metadata = obtain_access_token(settings)
    validator = build_access_token_validator(settings)
    principal = validator.validate(access_token)
    expected_capabilities = frozenset(Capability)
    if principal.capabilities != expected_capabilities:
        raise RuntimeError(
            "Synthetic reviewer capabilities were not normalized exactly."
        )
    delete_synthetic_principal(
        settings.database_url,
        issuer=principal.issuer,
        subject=principal.subject,
    )
    try:
        evidence = exercise_identity_boundary(
            settings=settings,
            access_token=access_token,
            public_metadata=public_metadata,
            validator=validator,
            principal=principal,
        )
    finally:
        delete_synthetic_principal(
            settings.database_url,
            issuer=principal.issuer,
            subject=principal.subject,
        )

    ARTIFACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIRECTORY / "identity-runtime-proof.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("OIDC authorization-code, PKCE, token, and principal proof passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
