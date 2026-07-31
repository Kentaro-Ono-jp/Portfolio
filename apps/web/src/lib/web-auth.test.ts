// @vitest-environment node

import { describe, expect, it, vi } from "vitest";

import { SessionStore } from "@/lib/auth-session-store";
import { OidcBoundaryError } from "@/lib/oidc";
import {
  CSRF_HEADER,
  cookieValue as readCookieValue,
  currentBrowserSession,
  finishSignIn,
  requireCsrf,
  requireWebSession,
  sanitizedAuthProblem,
  SESSION_COOKIE,
  signOut,
  startSignIn,
  TRANSACTION_COOKIE,
  WebAuthenticationError,
} from "@/lib/web-auth";

const NOW = 1_000_000;

function environment(): Record<string, string> {
  return {
    PORTFOLIO_API_BASE_URL: "http://api:8000",
    PORTFOLIO_WEB_PUBLIC_BASE_URL: "http://127.0.0.1:53000",
    PORTFOLIO_WEB_OIDC_ISSUER: "http://127.0.0.1:5556/dex",
    PORTFOLIO_WEB_OIDC_DISCOVERY_URL:
      "http://identity:5556/dex/.well-known/openid-configuration",
    PORTFOLIO_WEB_OIDC_TOKEN_URL: "http://identity:5556/dex/token",
    PORTFOLIO_WEB_OIDC_JWKS_URL: "http://identity:5556/dex/keys",
    PORTFOLIO_WEB_OIDC_CLIENT_ID: "reactorfront-api",
    PORTFOLIO_WEB_OIDC_ALLOW_INSECURE_LOOPBACK: "true",
  };
}

function store(): SessionStore {
  let index = 0;
  return new SessionStore({
    absoluteLifetimeMilliseconds: 28_800_000,
    inactivityLifetimeMilliseconds: 1_800_000,
    transactionLifetimeMilliseconds: 300_000,
    randomIdentifier: () => `${String(index++).padStart(32, "0")}identifier`,
  });
}

function cookieValue(setCookie: string, name: string): string {
  const match = new RegExp(`${name}=([^;]+)`).exec(setCookie);
  if (match?.[1] === undefined) {
    throw new Error(`Missing ${name} cookie.`);
  }
  return match[1];
}

describe("Web authentication boundary", () => {
  it("parses browser cookies without accepting empty values", () => {
    expect(readCookieValue(null, SESSION_COOKIE)).toBeUndefined();
    expect(readCookieValue("other=value", SESSION_COOKIE)).toBeUndefined();
    expect(
      readCookieValue(`${SESSION_COOKIE}=`, SESSION_COOKIE),
    ).toBeUndefined();
    expect(
      readCookieValue(`${SESSION_COOKIE}=opaque=value`, SESSION_COOKIE),
    ).toBe("opaque=value");
  });

  it("starts and completes sign-in with only opaque browser cookies", async () => {
    const sessions = store();
    const begin = vi.fn().mockResolvedValue({
      authorizationUrl: new URL(
        "http://127.0.0.1:5556/dex/auth?request=opaque",
      ),
      transaction: {
        state: "state",
        nonce: "nonce",
        codeVerifier: "verifier",
        returnTo: "/",
      },
    });
    const started = await startSignIn({
      environment: environment(),
      store: sessions,
      now: () => NOW,
      begin,
    });

    expect(started.status).toBe(302);
    expect(started.headers.get("Location")).toContain("/dex/auth");
    const transactionCookie = started.headers.get("Set-Cookie")!;
    expect(transactionCookie).toContain("HttpOnly");
    expect(transactionCookie).toContain("SameSite=Lax");
    expect(transactionCookie).not.toContain("verifier");
    const transactionId = cookieValue(transactionCookie, TRANSACTION_COOKIE);

    const complete = vi.fn().mockResolvedValue({
      subject: "synthetic-reviewer",
      tokens: {
        accessToken: "private-access-token",
        refreshToken: "private-refresh-token",
        idToken: "private-id-token",
        accessTokenExpiresAt: NOW + 300_000,
      },
    });
    const callback = new Request(
      "http://127.0.0.1:53000/api/auth/callback?code=code&state=state",
      { headers: { Cookie: `${TRANSACTION_COOKIE}=${transactionId}` } },
    );
    const finished = await finishSignIn(callback, {
      environment: environment(),
      store: sessions,
      now: () => NOW + 1,
      complete,
    });

    expect(finished.status).toBe(303);
    expect(finished.headers.get("Location")).toBe("/");
    const sessionCookies = finished.headers.get("Set-Cookie")!;
    expect(sessionCookies).toContain(SESSION_COOKIE);
    expect(sessionCookies).not.toContain("private-access-token");
    expect(sessionCookies).not.toContain("private-refresh-token");
    const sessionId = cookieValue(sessionCookies, SESSION_COOKIE);
    expect(
      currentBrowserSession(sessionId, {
        environment: environment(),
        store: sessions,
        now: () => NOW + 2,
      }),
    ).toMatchObject({ absoluteExpiresAt: NOW + 1 + 28_800_000 });
    expect(sessions.consumeTransaction(transactionId, NOW + 2)).toBeNull();
  });

  it("requires a live session, validates CSRF, and invalidates sign-out", async () => {
    const sessions = store();
    const session = sessions.createSession(
      {
        accessToken: "access",
        refreshToken: "refresh",
        accessTokenExpiresAt: NOW + 300_000,
      },
      "reviewer",
      NOW,
    );
    const request = new Request("http://web.test/api/documents", {
      method: "POST",
      headers: {
        Cookie: `${SESSION_COOKIE}=${session.id}`,
        [CSRF_HEADER]: session.csrfToken,
      },
    });
    const overrides = {
      environment: environment(),
      store: sessions,
      now: () => NOW + 1,
    };

    await expect(requireWebSession(request, overrides)).resolves.toMatchObject({
      accessToken: "access",
    });
    expect(() => requireCsrf(request, session, overrides)).not.toThrow();
    expect(signOut(request, overrides).status).toBe(204);
    await expect(requireWebSession(request, overrides)).rejects.toMatchObject({
      status: 401,
      code: "WEB_SESSION_REQUIRED",
    });
  });

  it("refreshes near-expiry tokens and fails closed without renewal", async () => {
    const sessions = store();
    const session = sessions.createSession(
      {
        accessToken: "expiring",
        refreshToken: "refresh",
        idToken: "id",
        accessTokenExpiresAt: NOW + 10_000,
      },
      "reviewer",
      NOW,
    );
    const request = new Request("http://web.test/api/documents", {
      headers: { Cookie: `${SESSION_COOKIE}=${session.id}` },
    });
    const refresh = vi.fn().mockResolvedValue({
      accessToken: "renewed",
      refreshToken: "refresh-2",
      accessTokenExpiresAt: NOW + 300_000,
    });
    await expect(
      requireWebSession(request, {
        environment: environment(),
        store: sessions,
        now: () => NOW + 1,
        refresh,
      }),
    ).resolves.toMatchObject({ accessToken: "renewed" });
    expect(refresh).toHaveBeenCalledWith(
      expect.anything(),
      "refresh",
      "reviewer",
      "id",
    );

    const noRefresh = sessions.createSession(
      { accessToken: "expired", accessTokenExpiresAt: NOW },
      "reviewer",
      NOW,
    );
    const expiredRequest = new Request("http://web.test/api/documents", {
      headers: { Cookie: `${SESSION_COOKIE}=${noRefresh.id}` },
    });
    await expect(
      requireWebSession(expiredRequest, {
        environment: environment(),
        store: sessions,
        now: () => NOW + 1,
      }),
    ).rejects.toMatchObject({ code: "WEB_SESSION_EXPIRED" });
  });

  it("sanitizes failed transactions, identity outages, and CSRF errors", async () => {
    const sessions = store();
    await expect(
      finishSignIn(new Request("http://web.test/api/auth/callback"), {
        environment: environment(),
        store: sessions,
        now: () => NOW,
      }),
    ).rejects.toMatchObject({ code: "WEB_AUTHENTICATION_FAILED" });

    await expect(
      startSignIn({
        environment: environment(),
        store: sessions,
        begin: vi.fn().mockRejectedValue(new OidcBoundaryError("private")),
      }),
    ).rejects.toMatchObject({ code: "WEB_IDENTITY_UNAVAILABLE" });

    const session = sessions.createSession(
      { accessToken: "access", accessTokenExpiresAt: NOW + 100_000 },
      "reviewer",
      NOW,
    );
    expect(() =>
      requireCsrf(
        new Request("http://web.test", {
          headers: { [CSRF_HEADER]: "wrong" },
        }),
        session,
        { environment: environment(), store: sessions, now: () => NOW },
      ),
    ).toThrow(WebAuthenticationError);

    const problem = sanitizedAuthProblem(
      new WebAuthenticationError(503, "WEB_PRIVATE", "Unavailable"),
    );
    expect(problem.status).toBe(503);
    expect(await problem.text()).not.toContain("private-access-token");
    expect(
      await sanitizedAuthProblem(
        new WebAuthenticationError(401, "WEB_SESSION_REQUIRED", "Sign in"),
      ).json(),
    ).toMatchObject({ detail: "Sign in again before retrying this request." });
  });

  it("maps callback validation failures while preserving unexpected defects", async () => {
    const sessions = store();
    const transactionId = sessions.createTransaction(
      { state: "s", nonce: "n", codeVerifier: "v", returnTo: "/" },
      NOW,
    );
    const request = new Request("http://web.test/api/auth/callback", {
      headers: { Cookie: `${TRANSACTION_COOKIE}=${transactionId}` },
    });
    await expect(
      finishSignIn(request, {
        environment: environment(),
        store: sessions,
        now: () => NOW,
        complete: vi.fn().mockRejectedValue(new OidcBoundaryError()),
      }),
    ).rejects.toMatchObject({ code: "WEB_AUTHENTICATION_FAILED" });

    const secondId = sessions.createTransaction(
      { state: "s", nonce: "n", codeVerifier: "v", returnTo: "/" },
      NOW,
    );
    await expect(
      finishSignIn(
        new Request("http://web.test/api/auth/callback", {
          headers: { Cookie: `${TRANSACTION_COOKIE}=${secondId}` },
        }),
        {
          environment: environment(),
          store: sessions,
          now: () => NOW,
          complete: vi.fn().mockRejectedValue(new TypeError("defect")),
        },
      ),
    ).rejects.toThrow("defect");
    await expect(
      startSignIn({
        environment: environment(),
        store: sessions,
        begin: vi.fn().mockRejectedValue(new TypeError("defect")),
      }),
    ).rejects.toThrow("defect");
  });

  it("handles refresh races and temporary refresh outages without leaking a session", async () => {
    const sessions = store();
    const live = sessions.createSession(
      {
        accessToken: "still-live",
        refreshToken: "refresh",
        accessTokenExpiresAt: NOW + 10_000,
      },
      "reviewer",
      NOW,
    );
    const requestFor = (id: string) =>
      new Request("http://web.test/api/documents", {
        headers: { Cookie: `${SESSION_COOKIE}=${id}` },
      });
    await expect(
      requireWebSession(requestFor(live.id), {
        environment: environment(),
        store: sessions,
        now: () => NOW + 1,
        refresh: vi.fn().mockRejectedValue(new OidcBoundaryError()),
      }),
    ).resolves.toMatchObject({ accessToken: "still-live" });

    const expired = sessions.createSession(
      {
        accessToken: "expired",
        refreshToken: "refresh",
        accessTokenExpiresAt: NOW,
      },
      "reviewer",
      NOW,
    );
    await expect(
      requireWebSession(requestFor(expired.id), {
        environment: environment(),
        store: sessions,
        now: () => NOW + 1,
        refresh: vi.fn().mockRejectedValue(new OidcBoundaryError()),
      }),
    ).rejects.toMatchObject({ code: "WEB_SESSION_EXPIRED" });
    expect(sessions.getSession(expired.id, NOW + 1)).toBeNull();

    const raced = sessions.createSession(
      {
        accessToken: "expired",
        refreshToken: "refresh",
        accessTokenExpiresAt: NOW,
      },
      "reviewer",
      NOW,
    );
    const replace = vi
      .spyOn(sessions, "replaceTokens")
      .mockReturnValueOnce(null);
    await expect(
      requireWebSession(requestFor(raced.id), {
        environment: environment(),
        store: sessions,
        now: () => NOW + 1,
        refresh: vi.fn().mockResolvedValue({
          accessToken: "new",
          accessTokenExpiresAt: NOW + 100_000,
        }),
      }),
    ).rejects.toMatchObject({ code: "WEB_SESSION_EXPIRED" });
    replace.mockRestore();
  });

  it("rejects anonymous or forged sign-out and renders no expired browser session", () => {
    const sessions = store();
    const overrides = {
      environment: environment(),
      store: sessions,
      now: () => NOW,
    };
    expect(currentBrowserSession(undefined, overrides)).toBeNull();
    expect(() => signOut(new Request("http://web.test"), overrides)).toThrow(
      WebAuthenticationError,
    );
    const session = sessions.createSession(
      { accessToken: "access", accessTokenExpiresAt: NOW + 100_000 },
      "reviewer",
      NOW,
    );
    expect(() =>
      signOut(
        new Request("http://web.test", {
          headers: {
            Cookie: `${SESSION_COOKIE}=${session.id}`,
            [CSRF_HEADER]: "forged",
          },
        }),
        overrides,
      ),
    ).toThrow(WebAuthenticationError);
  });
});
