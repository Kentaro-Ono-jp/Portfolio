from __future__ import annotations

import base64
import hashlib
import json
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from typing import Protocol
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    Request,
    build_opener,
    urlopen,
)

CLIENT_ID = "reactorfront-api"
REDIRECT_URI = "http://127.0.0.1:5557/callback"
SYNTHETIC_EMAIL = "reviewer@synthetic.invalid"
SYNTHETIC_PASSWORD = "password"
STATE = "reactorfront-synthetic-state"
NONCE = "reactorfront-synthetic-nonce"
VERIFIER = "reactorfront-synthetic-pkce-verifier-000000000000000000000000"


class OidcSettings(Protocol):
    oidc_discovery_url: str
    oidc_issuer: str


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
        self.action = dict(attrs).get("action")


class CallbackReached(Exception):
    def __init__(self, location: str) -> None:
        super().__init__("OIDC callback reached.")
        self.location = location


class CallbackRedirectHandler(HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        request: Request,
        file_pointer: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> Request | None:
        location = urljoin(request.full_url, new_url)
        if location.startswith(REDIRECT_URI):
            raise CallbackReached(location)
        return super().redirect_request(
            request,
            file_pointer,
            code,
            message,
            headers,
            new_url,
        )


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _json_request(url: str, *, data: dict[str, str] | None = None) -> object:
    encoded = None if data is None else urlencode(data).encode("ascii")
    request = Request(
        url,
        data=encoded,
        headers={
            "Accept": "application/json",
            **(
                {}
                if encoded is None
                else {"Content-Type": "application/x-www-form-urlencoded"}
            ),
        },
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def obtain_access_token(settings: OidcSettings) -> tuple[str, dict[str, object]]:
    metadata = _json_request(settings.oidc_discovery_url)
    if not isinstance(metadata, dict) or metadata.get("issuer") != settings.oidc_issuer:
        raise RuntimeError("OIDC discovery returned an unexpected issuer.")
    authorization_endpoint = metadata.get("authorization_endpoint")
    token_endpoint = metadata.get("token_endpoint")
    if not isinstance(authorization_endpoint, str) or not isinstance(
        token_endpoint, str
    ):
        raise RuntimeError("OIDC discovery omitted required endpoints.")

    authorization_url = f"{authorization_endpoint}?{
        urlencode(
            {
                'client_id': CLIENT_ID,
                'redirect_uri': REDIRECT_URI,
                'response_type': 'code',
                'scope': 'openid groups',
                'state': STATE,
                'nonce': NONCE,
                'code_challenge': pkce_challenge(VERIFIER),
                'code_challenge_method': 'S256',
            }
        )
    }"
    opener = build_opener(
        HTTPCookieProcessor(CookieJar()),
        CallbackRedirectHandler(),
    )
    with opener.open(authorization_url, timeout=5) as response:
        login_url = response.geturl()
        login_form = response.read().decode("utf-8")
    parser = FormActionParser()
    parser.feed(login_form)
    if parser.action is None:
        raise RuntimeError("OIDC synthetic login form omitted its action.")

    login_request = Request(
        urljoin(login_url, parser.action),
        data=urlencode(
            {"login": SYNTHETIC_EMAIL, "password": SYNTHETIC_PASSWORD}
        ).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        opener.open(login_request, timeout=5)
    except CallbackReached as callback_reached:
        callback = callback_reached.location
    else:
        raise RuntimeError("OIDC authorization code callback was not produced.")

    query = parse_qs(urlparse(callback).query)
    if query.get("state") != [STATE] or len(query.get("code", [])) != 1:
        raise RuntimeError("OIDC callback state or authorization code was invalid.")
    token_payload = _json_request(
        token_endpoint,
        data={
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code": query["code"][0],
            "code_verifier": VERIFIER,
        },
    )
    if not isinstance(token_payload, dict):
        raise RuntimeError("OIDC token response was not a JSON object.")
    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("OIDC token response omitted the access token.")
    return access_token, {
        "tokenType": token_payload.get("token_type"),
        "expiresIn": token_payload.get("expires_in"),
        "authorizationCodePkce": True,
    }
