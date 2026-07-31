// @vitest-environment node

import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("openid-client", () => ({
  Configuration: class {
    timeout?: number;
  },
  None: vi.fn(() => "none"),
  ClientSecretPost: vi.fn(() => "secret-post"),
  allowInsecureRequests: vi.fn(),
  randomPKCECodeVerifier: vi.fn(() => "pkce-verifier"),
  randomState: vi.fn(() => "state"),
  randomNonce: vi.fn(() => "nonce"),
  calculatePKCECodeChallenge: vi.fn(async () => "pkce-challenge"),
  buildAuthorizationUrl: vi.fn(
    (_configuration, parameters: Record<string, string>) =>
      new URL(
        `http://127.0.0.1:5556/dex/auth?${new URLSearchParams(parameters)}`,
      ),
  ),
  authorizationCodeGrant: vi.fn(),
  refreshTokenGrant: vi.fn(),
}));

import * as client from "openid-client";

import {
  beginAuthorization,
  completeAuthorization,
  OidcBoundaryError,
  refreshAuthorization,
} from "@/lib/oidc";
import type { ServerConfig } from "@/lib/server-config";

const NOW = 1_000_000;

function settings(): ServerConfig {
  return {
    apiBaseUrl: "http://api:8000",
    timeoutMilliseconds: 1_000,
    publicBaseUrl: "http://127.0.0.1:53000",
    oidcIssuer: "http://127.0.0.1:5556/dex",
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
  };
}

function metadata(overrides: Record<string, unknown> = {}): object {
  return {
    issuer: "http://127.0.0.1:5556/dex",
    authorization_endpoint: "http://127.0.0.1:5556/dex/auth",
    token_endpoint: "http://127.0.0.1:5556/dex/token",
    jwks_uri: "http://127.0.0.1:5556/dex/keys",
    response_types_supported: ["code"],
    grant_types_supported: ["authorization_code", "refresh_token"],
    code_challenge_methods_supported: ["S256"],
    id_token_signing_alg_values_supported: ["RS256"],
    ...overrides,
  };
}

function discovery(payload: object = metadata()): typeof fetch {
  return vi.fn<typeof fetch>().mockResolvedValue(
    Response.json(payload, {
      headers: { "Content-Length": String(JSON.stringify(payload).length) },
    }),
  );
}

function tokenResponse(overrides: Record<string, unknown> = {}): object {
  return {
    access_token: "access",
    refresh_token: "refresh",
    id_token: "id",
    claims: () => ({ sub: "synthetic-reviewer" }),
    expiresIn: () => 300,
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(client.authorizationCodeGrant).mockReset();
  vi.mocked(client.refreshTokenGrant).mockReset();
  vi.mocked(client.allowInsecureRequests).mockClear();
});

describe("OIDC client boundary", () => {
  it("builds a state, nonce, and S256 PKCE authorization request", async () => {
    const result = await beginAuthorization(settings(), { fetch: discovery() });

    expect(result.transaction).toEqual({
      state: "state",
      nonce: "nonce",
      codeVerifier: "pkce-verifier",
      returnTo: "/",
    });
    expect(result.authorizationUrl.searchParams.get("code_challenge")).toBe(
      "pkce-challenge",
    );
    expect(result.authorizationUrl.searchParams.get("scope")).toContain(
      "openid",
    );
    expect(client.allowInsecureRequests).toHaveBeenCalledOnce();
  });

  it("validates the trusted callback and returns only bounded token state", async () => {
    vi.mocked(client.authorizationCodeGrant).mockResolvedValue(
      tokenResponse() as never,
    );
    const transaction = {
      state: "state",
      nonce: "nonce",
      codeVerifier: "verifier",
      returnTo: "/",
    };

    const result = await completeAuthorization(
      settings(),
      "http://attacker.invalid/callback?code=code&state=state",
      transaction,
      { fetch: discovery(), now: () => NOW },
    );

    expect(result).toEqual({
      subject: "synthetic-reviewer",
      tokens: {
        accessToken: "access",
        accessTokenExpiresAt: NOW + 300_000,
        refreshToken: "refresh",
        idToken: "id",
      },
    });
    const [, callback, checks] = vi.mocked(client.authorizationCodeGrant).mock
      .calls[0]!;
    expect((callback as URL).origin).toBe("http://127.0.0.1:53000");
    expect(checks).toEqual({
      expectedState: "state",
      expectedNonce: "nonce",
      pkceCodeVerifier: "verifier",
    });
  });

  it("refreshes access tokens without losing a rotated or retained refresh token", async () => {
    vi.mocked(client.refreshTokenGrant).mockResolvedValue(
      tokenResponse({ id_token: undefined, refresh_token: undefined }) as never,
    );
    await expect(
      refreshAuthorization(
        settings(),
        "refresh-1",
        "synthetic-reviewer",
        "id-1",
        {
          fetch: discovery(),
          now: () => NOW,
        },
      ),
    ).resolves.toEqual({
      accessToken: "access",
      accessTokenExpiresAt: NOW + 300_000,
      refreshToken: "refresh-1",
      idToken: "id-1",
    });
  });

  it("fails closed for malformed discovery, endpoint drift, and grant output", async () => {
    const invalidMetadata = [
      metadata({ issuer: "http://wrong.invalid/dex" }),
      metadata({ authorization_endpoint: "http://wrong.invalid/dex/auth" }),
      metadata({ token_endpoint: "http://127.0.0.1:5556/wrong" }),
      metadata({ jwks_uri: "http://127.0.0.1:5556/wrong" }),
      metadata({ response_types_supported: [] }),
      metadata({ grant_types_supported: [] }),
      metadata({ code_challenge_methods_supported: [] }),
      metadata({ id_token_signing_alg_values_supported: [] }),
    ];
    for (const payload of invalidMetadata) {
      await expect(
        beginAuthorization(settings(), { fetch: discovery(payload) }),
      ).rejects.toBeInstanceOf(OidcBoundaryError);
    }

    vi.mocked(client.authorizationCodeGrant).mockResolvedValue(
      tokenResponse({ claims: () => undefined }) as never,
    );
    await expect(
      completeAuthorization(
        settings(),
        "http://web.test/callback",
        { state: "s", nonce: "n", codeVerifier: "v", returnTo: "/" },
        { fetch: discovery(), now: () => NOW },
      ),
    ).rejects.toBeInstanceOf(OidcBoundaryError);

    await expect(
      beginAuthorization(settings(), {
        fetch: vi.fn<typeof fetch>().mockRejectedValue(new Error("private")),
      }),
    ).rejects.toBeInstanceOf(OidcBoundaryError);
  });

  it("bounds discovery transport and JSON parsing failures", async () => {
    const failures: Array<typeof fetch> = [
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response("failure", { status: 503 })),
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(
          new Response("{}", { headers: { "Content-Length": "65537" } }),
        ),
      vi.fn<typeof fetch>().mockResolvedValue(new Response("x".repeat(65_537))),
      vi.fn<typeof fetch>().mockResolvedValue(new Response("not-json")),
      vi.fn<typeof fetch>().mockResolvedValue({
        ok: true,
        headers: new Headers(),
        text: vi.fn().mockRejectedValue(new Error("stream failed")),
      } as unknown as Response),
    ];
    for (const fetchImplementation of failures) {
      await expect(
        beginAuthorization(settings(), { fetch: fetchImplementation }),
      ).rejects.toBeInstanceOf(OidcBoundaryError);
    }
  });

  it("supports confidential HTTPS clients and optional discovery metadata", async () => {
    const secure = {
      ...settings(),
      publicBaseUrl: "https://portfolio.example",
      oidcIssuer: "https://identity.example/dex",
      oidcDiscoveryUrl:
        "https://identity.example/dex/.well-known/openid-configuration",
      oidcTokenUrl: "https://identity.example/dex/token",
      oidcJwksUrl: "https://identity.example/dex/keys",
      redirectUri: "https://portfolio.example/api/auth/callback",
      oidcClientSecret: "secret",
      allowInsecureLoopback: false,
      secureCookies: true,
    };
    const payload = metadata({
      issuer: secure.oidcIssuer,
      authorization_endpoint: "https://identity.example/dex/auth",
      token_endpoint: secure.oidcTokenUrl,
      jwks_uri: secure.oidcJwksUrl,
      grant_types_supported: undefined,
      code_challenge_methods_supported: undefined,
    });
    await expect(
      beginAuthorization(secure, { fetch: discovery(payload) }),
    ).resolves.toHaveProperty("transaction.state", "state");
    expect(client.ClientSecretPost).toHaveBeenCalledWith("secret");
    expect(client.allowInsecureRequests).not.toHaveBeenCalled();
  });

  it("rejects invalid token fields and subject-changing refreshes", async () => {
    const invalidGrants = [
      tokenResponse({ claims: () => ({ sub: "" }) }),
      tokenResponse({ claims: () => ({ sub: "x".repeat(256) }) }),
      tokenResponse({ access_token: "" }),
      tokenResponse({ expiresIn: () => undefined }),
      tokenResponse({ expiresIn: () => 0 }),
    ];
    for (const grant of invalidGrants) {
      vi.mocked(client.authorizationCodeGrant).mockResolvedValueOnce(
        grant as never,
      );
      await expect(
        completeAuthorization(
          settings(),
          "http://web.test/callback",
          { state: "s", nonce: "n", codeVerifier: "v", returnTo: "/" },
          { fetch: discovery(), now: () => NOW },
        ),
      ).rejects.toBeInstanceOf(OidcBoundaryError);
    }

    vi.mocked(client.refreshTokenGrant).mockResolvedValueOnce(
      tokenResponse({ claims: () => ({ sub: "another-user" }) }) as never,
    );
    await expect(
      refreshAuthorization(
        settings(),
        "refresh",
        "synthetic-reviewer",
        undefined,
        {
          fetch: discovery(),
          now: () => NOW,
        },
      ),
    ).rejects.toBeInstanceOf(OidcBoundaryError);

    vi.mocked(client.refreshTokenGrant).mockRejectedValueOnce(
      new Error("private"),
    );
    await expect(
      refreshAuthorization(
        settings(),
        "refresh",
        "synthetic-reviewer",
        undefined,
        {
          fetch: discovery(),
          now: () => NOW,
        },
      ),
    ).rejects.toBeInstanceOf(OidcBoundaryError);
  });
});
