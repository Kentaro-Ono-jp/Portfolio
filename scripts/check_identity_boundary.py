from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PROJECT_NAME = "reactorfront-portfolio"
DEX_IMAGE = (
    "ghcr.io/dexidp/dex:v2.45.1@"
    "sha256:8499afd690c437f52301efd2b05b2455da5bd2dfc20332cd697dc9937f808462"
)


def expected_loopback_web_public_base(web: dict[str, object]) -> str:
    ports = web.get("ports")
    if not isinstance(ports, list) or len(ports) != 1:
        raise RuntimeError("Web must expose one loopback-only public port.")
    port = ports[0]
    if (
        not isinstance(port, dict)
        or port.get("host_ip") != "127.0.0.1"
        or str(port.get("target")) != "3000"
    ):
        raise RuntimeError("Web must expose one loopback-only public port.")
    published = str(port.get("published", ""))
    if not published.isdecimal() or not 1 <= int(published) <= 65535:
        raise RuntimeError("Web must publish one valid host port.")
    return f"http://127.0.0.1:{published}"


def main() -> int:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            COMPOSE_PROJECT_NAME,
            "config",
            "--format",
            "json",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    config = json.loads(result.stdout)
    identity = config["services"].get("identity")
    if identity is None:
        raise RuntimeError("The protocol-faithful test identity service is missing.")
    if identity.get("image") != DEX_IMAGE:
        raise RuntimeError("The Dex tag and manifest digest are not pinned exactly.")
    ports = identity.get("ports", [])
    if (
        len(ports) != 1
        or ports[0].get("host_ip") != "127.0.0.1"
        or ports[0].get("target") != 5556
    ):
        raise RuntimeError("Dex must expose one loopback-only test port.")
    if identity.get("environment"):
        raise RuntimeError("Dex must not require environment credentials.")
    volumes = identity.get("volumes", [])
    if len(volumes) != 1 or not volumes[0].get("read_only"):
        raise RuntimeError("Dex must use one read-only repository-owned configuration.")
    api_environment = config["services"]["api"].get("environment", {})
    if (
        api_environment.get("PORTFOLIO_OIDC_ISSUER") != "http://127.0.0.1:5556/dex"
        or api_environment.get("PORTFOLIO_OIDC_DISCOVERY_URL")
        != "http://identity:5556/dex/.well-known/openid-configuration"
        or api_environment.get("PORTFOLIO_OIDC_JWKS_URL")
        != "http://identity:5556/dex/keys"
        or api_environment.get("PORTFOLIO_OIDC_MODE") != "dex"
    ):
        raise RuntimeError(
            "The API must validate the public issuer through the Dex backchannel."
        )
    web = config["services"]["web"]
    web_public_base = expected_loopback_web_public_base(web)
    web_environment = web.get("environment", {})
    required_web_environment = {
        "PORTFOLIO_WEB_PUBLIC_BASE_URL": web_public_base,
        "PORTFOLIO_WEB_OIDC_ISSUER": "http://127.0.0.1:5556/dex",
        "PORTFOLIO_WEB_OIDC_AUTHORIZATION_URL": "http://127.0.0.1:5556/dex/auth",
        "PORTFOLIO_WEB_OIDC_DISCOVERY_URL": (
            "http://identity:5556/dex/.well-known/openid-configuration"
        ),
        "PORTFOLIO_WEB_OIDC_TOKEN_URL": "http://identity:5556/dex/token",
        "PORTFOLIO_WEB_OIDC_JWKS_URL": "http://identity:5556/dex/keys",
        "PORTFOLIO_WEB_OIDC_CLIENT_ID": "reactorfront-api",
        "PORTFOLIO_WEB_OIDC_ALLOW_INSECURE_LOOPBACK": "true",
    }
    if any(
        web_environment.get(name) != value
        for name, value in required_web_environment.items()
    ):
        raise RuntimeError(
            "The Web OIDC session must use the public issuer and internal "
            "Dex backchannels in the loopback Compose profile."
        )

    dex_config = (
        REPOSITORY_ROOT / "infra" / "docker" / "identity" / "dex.yaml"
    ).read_text(encoding="utf-8")
    required_config = (
        "grantTypes:\n    - authorization_code",
        "responseTypes:\n    - code",
        "public: true",
        f"{web_public_base}/api/auth/callback",
        "reviewer@synthetic.invalid",
        "reactorfront-reviewers",
    )
    for required in required_config:
        if required not in dex_config:
            raise RuntimeError(f"Dex configuration is missing: {required}")
    for forbidden in ("client_credentials", "\n    - password\n", "implicit"):
        if forbidden in dex_config:
            raise RuntimeError(f"Dex enables a forbidden grant or flow: {forbidden}")

    api_project = tomllib.loads(
        (REPOSITORY_ROOT / "apps" / "api" / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )
    if "pyjwt[crypto]==2.13.0" not in api_project["project"]["dependencies"]:
        raise RuntimeError("The reviewed PyJWT cryptographic dependency is not pinned.")
    web_package = json.loads(
        (REPOSITORY_ROOT / "apps" / "web" / "package.json").read_text(encoding="utf-8")
    )
    if web_package["dependencies"].get("openid-client") != "6.8.4":
        raise RuntimeError("The reviewed openid-client dependency is not pinned.")
    notices = (REPOSITORY_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for required_notice in (
        "Dex",
        "v2.45.1",
        "Apache-2.0",
        "PyJWT",
        "2.13.0",
        "openid-client",
        "6.8.4",
        "MIT",
    ):
        if required_notice not in notices:
            raise RuntimeError(f"Third-party notices omit {required_notice}.")
    print(
        "Identity boundary passed: pinned Dex, authorization-code-only test flow, "
        "loopback exposure, synthetic identity, pinned JWT verification, and "
        "server-owned Web OIDC session configuration."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
