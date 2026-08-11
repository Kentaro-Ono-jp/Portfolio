import { describe, expect, it } from "vitest";

import {
  InvalidServerConfigurationError,
  readServerConfig,
} from "@/lib/server-config";

function loopbackEnvironment(): Record<string, string> {
  return {
    PORTFOLIO_API_BASE_URL: "http://api:8000/",
    PORTFOLIO_WEB_PUBLIC_BASE_URL: "http://127.0.0.1:53000/",
    PORTFOLIO_WEB_OIDC_ISSUER: "http://127.0.0.1:5556/dex/",
    PORTFOLIO_WEB_OIDC_AUTHORIZATION_URL: "http://127.0.0.1:5556/dex/auth",
    PORTFOLIO_WEB_OIDC_DISCOVERY_URL:
      "http://identity:5556/dex/.well-known/openid-configuration",
    PORTFOLIO_WEB_OIDC_TOKEN_URL: "http://identity:5556/dex/token",
    PORTFOLIO_WEB_OIDC_JWKS_URL: "http://identity:5556/dex/keys",
    PORTFOLIO_WEB_OIDC_CLIENT_ID: "reactorfront-api",
    PORTFOLIO_WEB_OIDC_ALLOW_INSECURE_LOOPBACK: "true",
  };
}

describe("readServerConfig", () => {
  it("normalizes the bounded loopback development configuration", () => {
    expect(readServerConfig(loopbackEnvironment())).toEqual({
      apiBaseUrl: "http://api:8000",
      timeoutMilliseconds: 8_000,
      publicBaseUrl: "http://127.0.0.1:53000",
      oidcIssuer: "http://127.0.0.1:5556/dex",
      oidcAuthorizationUrl: "http://127.0.0.1:5556/dex/auth",
      oidcDiscoveryUrl:
        "http://identity:5556/dex/.well-known/openid-configuration",
      oidcTokenUrl: "http://identity:5556/dex/token",
      oidcJwksUrl: "http://identity:5556/dex/keys",
      oidcClientId: "reactorfront-api",
      oidcScopes: "openid groups offline_access",
      allowInsecureLoopback: true,
      sessionAbsoluteSeconds: 28_800,
      sessionInactivitySeconds: 1_800,
      oidcTransactionSeconds: 300,
      tokenRefreshLeewaySeconds: 30,
      secureCookies: false,
      redirectUri: "http://127.0.0.1:53000/api/auth/callback",
    });
  });

  it("accepts HTTPS production endpoints, a secret, and bounded overrides", () => {
    const environment = loopbackEnvironment();
    Object.assign(environment, {
      PORTFOLIO_API_BASE_URL: "https://api.example.test/base",
      PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS: "1500",
      PORTFOLIO_WEB_PUBLIC_BASE_URL: "https://portfolio.example.test",
      PORTFOLIO_WEB_OIDC_ISSUER: "https://identity.example.test/dex",
      PORTFOLIO_WEB_OIDC_AUTHORIZATION_URL:
        "https://identity.example.test/dex/auth",
      PORTFOLIO_WEB_OIDC_DISCOVERY_URL:
        "https://identity.internal.test/dex/.well-known/openid-configuration",
      PORTFOLIO_WEB_OIDC_TOKEN_URL: "https://identity.internal.test/dex/token",
      PORTFOLIO_WEB_OIDC_JWKS_URL: "https://identity.internal.test/dex/keys",
      PORTFOLIO_WEB_OIDC_CLIENT_SECRET: "runtime-only-secret",
      PORTFOLIO_WEB_OIDC_RESOURCE: "https://api.example.test/resource/",
      PORTFOLIO_WEB_OIDC_ALLOW_INSECURE_LOOPBACK: "false",
      PORTFOLIO_WEB_SESSION_ABSOLUTE_SECONDS: "3600",
      PORTFOLIO_WEB_SESSION_INACTIVITY_SECONDS: "600",
    });

    expect(readServerConfig(environment)).toMatchObject({
      apiBaseUrl: "https://api.example.test/base",
      timeoutMilliseconds: 1_500,
      oidcClientSecret: "runtime-only-secret",
      oidcResource: "https://api.example.test/resource",
      secureCookies: true,
      sessionAbsoluteSeconds: 3_600,
      sessionInactivitySeconds: 600,
    });
  });

  it("rejects missing, malformed, insecure, and non-OIDC configuration", () => {
    const invalid = [
      {},
      { ...loopbackEnvironment(), PORTFOLIO_API_BASE_URL: "not a URL" },
      {
        ...loopbackEnvironment(),
        PORTFOLIO_WEB_PUBLIC_BASE_URL: "http://public.example.test",
      },
      {
        ...loopbackEnvironment(),
        PORTFOLIO_WEB_OIDC_AUTHORIZATION_URL:
          "http://public.example.test/oauth2/authorize",
      },
      {
        ...loopbackEnvironment(),
        PORTFOLIO_WEB_OIDC_SCOPES: "groups offline_access",
      },
      {
        ...loopbackEnvironment(),
        PORTFOLIO_WEB_OIDC_RESOURCE: "not a URL",
      },
      {
        ...loopbackEnvironment(),
        PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS: "0",
      },
    ];
    for (const environment of invalid) {
      expect(() => readServerConfig(environment)).toThrow(
        InvalidServerConfigurationError,
      );
    }
  });
});
