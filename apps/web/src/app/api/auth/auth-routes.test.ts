// @vitest-environment node

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  finishSignIn,
  requireWebSession,
  sanitizedAuthProblem,
  signOut,
  startSignIn,
  WebAuthenticationError,
} from "@/lib/web-auth";

vi.mock("@/lib/web-auth", () => {
  class MockWebAuthenticationError extends Error {
    constructor(
      readonly status: number,
      readonly code: string,
      message: string,
    ) {
      super(message);
    }
  }
  return {
    startSignIn: vi.fn(),
    finishSignIn: vi.fn(),
    signOut: vi.fn(),
    requireWebSession: vi.fn(),
    sanitizedAuthProblem: vi.fn((error: MockWebAuthenticationError) =>
      Response.json({ code: error.code }, { status: error.status }),
    ),
    WebAuthenticationError: MockWebAuthenticationError,
  };
});

import { GET as callback } from "./callback/route";
import { GET as session } from "./session/route";
import { GET as signIn } from "./sign-in/route";
import { POST as signOutRoute } from "./sign-out/route";

beforeEach(() => {
  vi.mocked(startSignIn).mockReset();
  vi.mocked(finishSignIn).mockReset();
  vi.mocked(signOut).mockReset();
  vi.mocked(requireWebSession).mockReset();
  vi.mocked(sanitizedAuthProblem).mockClear();
});

describe("authentication route handlers", () => {
  it("delegates sign-in, callback, and sign-out success responses", async () => {
    const redirect = new Response(null, { status: 302 });
    const completed = new Response(null, { status: 303 });
    const signedOut = new Response(null, { status: 204 });
    vi.mocked(startSignIn).mockResolvedValue(redirect);
    vi.mocked(finishSignIn).mockResolvedValue(completed);
    vi.mocked(signOut).mockReturnValue(signedOut);
    const request = new Request("http://web.test/api/auth/callback");

    await expect(signIn()).resolves.toBe(redirect);
    await expect(callback(request)).resolves.toBe(completed);
    await expect(signOutRoute(request)).resolves.toBe(signedOut);
  });

  it("returns only sanitized authentication problems", async () => {
    const failure = new WebAuthenticationError(
      401,
      "WEB_AUTHENTICATION_FAILED",
      "Invalid",
    );
    vi.mocked(startSignIn).mockRejectedValue(failure);
    vi.mocked(finishSignIn).mockRejectedValue(failure);
    vi.mocked(signOut).mockImplementation(() => {
      throw failure;
    });

    expect((await signIn()).status).toBe(401);
    expect(
      (await callback(new Request("http://web.test/api/auth/callback"))).status,
    ).toBe(401);
    expect(
      (await signOutRoute(new Request("http://web.test/api/auth/sign-out")))
        .status,
    ).toBe(401);
    expect(sanitizedAuthProblem).toHaveBeenCalledTimes(3);
  });

  it("exposes bounded session metadata without OAuth tokens", async () => {
    vi.mocked(requireWebSession).mockResolvedValue({
      csrfToken: "csrf",
      absoluteExpiresAt: Date.parse("2026-07-31T12:00:00Z"),
      accessToken: "private",
    } as never);

    const response = await session(
      new Request("http://web.test/api/auth/session"),
    );
    const text = await response.text();
    expect(response.status).toBe(200);
    expect(JSON.parse(text)).toEqual({
      authenticated: true,
      csrfToken: "csrf",
      expiresAt: "2026-07-31T12:00:00.000Z",
    });
    expect(text).not.toContain("private");
  });

  it("maps unexpected route failures to sanitized availability problems", async () => {
    vi.mocked(startSignIn).mockRejectedValue(new Error("private"));
    vi.mocked(finishSignIn).mockRejectedValue(new Error("private"));
    vi.mocked(signOut).mockImplementation(() => {
      throw new Error("private");
    });
    vi.mocked(requireWebSession).mockRejectedValue(new Error("private"));

    expect((await signIn()).status).toBe(503);
    expect(
      (await callback(new Request("http://web.test/api/auth/callback"))).status,
    ).toBe(503);
    expect(
      (await signOutRoute(new Request("http://web.test/api/auth/sign-out")))
        .status,
    ).toBe(503);
    expect(
      (await session(new Request("http://web.test/api/auth/session"))).status,
    ).toBe(503);
  });

  it("preserves a sanitized session error", async () => {
    vi.mocked(requireWebSession).mockRejectedValue(
      new WebAuthenticationError(401, "WEB_SESSION_REQUIRED", "Required"),
    );
    const response = await session(
      new Request("http://web.test/api/auth/session"),
    );
    expect(response.status).toBe(401);
  });
});
