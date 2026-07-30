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
    ):
        raise RuntimeError(
            "The API must validate the public issuer through the Dex backchannel."
        )

    dex_config = (
        REPOSITORY_ROOT / "infra" / "docker" / "identity" / "dex.yaml"
    ).read_text(encoding="utf-8")
    required_config = (
        "grantTypes:\n    - authorization_code",
        "responseTypes:\n    - code",
        "public: true",
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
    notices = (REPOSITORY_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for required_notice in ("Dex", "v2.45.1", "Apache-2.0", "PyJWT", "2.13.0", "MIT"):
        if required_notice not in notices:
            raise RuntimeError(f"Third-party notices omit {required_notice}.")
    print(
        "Identity boundary passed: pinned Dex, authorization-code-only test flow, "
        "loopback exposure, synthetic identity, and pinned JWT verification."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
