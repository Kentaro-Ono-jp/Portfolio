// @vitest-environment node

import { describe, expect, it } from "vitest";

import { SessionStore } from "@/lib/auth-session-store";

function identifiers(): () => string {
  let index = 0;
  return () => `${String(index++).padStart(32, "0")}identifier`;
}

function store(maximumEntries = 4): SessionStore {
  return new SessionStore({
    absoluteLifetimeMilliseconds: 1_000,
    inactivityLifetimeMilliseconds: 200,
    transactionLifetimeMilliseconds: 100,
    maximumEntries,
    randomIdentifier: identifiers(),
  });
}

describe("SessionStore", () => {
  it("consumes each bounded OIDC transaction exactly once", () => {
    const sessions = store();
    const transaction = {
      state: "state",
      nonce: "nonce",
      codeVerifier: "verifier",
      returnTo: "/",
    };
    const id = sessions.createTransaction(transaction, 1_000);

    expect(sessions.consumeTransaction(id, 1_099)).toEqual(transaction);
    expect(sessions.consumeTransaction(id, 1_099)).toBeNull();
    const expired = sessions.createTransaction(transaction, 2_000);
    expect(sessions.consumeTransaction(expired, 2_100)).toBeNull();
    expect(sessions.consumeTransaction(undefined, 2_100)).toBeNull();
  });

  it("enforces absolute and inactivity expiry while supporting token renewal", () => {
    const sessions = store();
    const created = sessions.createSession(
      { accessToken: "access-1", accessTokenExpiresAt: 1_500 },
      "reviewer",
      1_000,
    );

    expect(sessions.getSession(created.id, 1_100)?.lastSeenAt).toBe(1_100);
    expect(sessions.csrfMatches(created, created.csrfToken)).toBe(true);
    expect(sessions.csrfMatches(created, "wrong")).toBe(false);
    expect(sessions.csrfMatches(created, null)).toBe(false);

    const renewed = sessions.replaceTokens(
      created.id,
      {
        accessToken: "access-2",
        accessTokenExpiresAt: 2_000,
        refreshToken: "refresh-2",
      },
      1_150,
    );
    expect(renewed).toMatchObject({
      accessToken: "access-2",
      refreshToken: "refresh-2",
      csrfToken: created.csrfToken,
      absoluteExpiresAt: 2_000,
    });

    expect(sessions.getSession(created.id, 1_351)).toBeNull();
    expect(sessions.replaceTokens(created.id, created, 1_352)).toBeNull();

    const absolute = sessions.createSession(
      { accessToken: "access", accessTokenExpiresAt: 5_000 },
      "reviewer",
      2_000,
    );
    expect(sessions.getSession(absolute.id, 3_000)).toBeNull();
    sessions.deleteSession(undefined);
  });

  it("bounds capacity and removes an explicitly signed-out session", () => {
    const sessions = store(1);
    const first = sessions.createSession(
      { accessToken: "first", accessTokenExpiresAt: 10_000 },
      "reviewer",
      1,
    );
    const second = sessions.createSession(
      { accessToken: "second", accessTokenExpiresAt: 10_000 },
      "reviewer",
      2,
    );
    expect(sessions.getSession(first.id, 3)).toBeNull();
    expect(sessions.getSession(second.id, 3, false)).not.toBeNull();
    sessions.deleteSession(second.id);
    expect(sessions.getSession(second.id, 3)).toBeNull();
  });

  it("rejects invalid lifetimes, capacity, and repeated weak identifiers", () => {
    expect(
      () =>
        new SessionStore({
          absoluteLifetimeMilliseconds: 0,
          inactivityLifetimeMilliseconds: 1,
          transactionLifetimeMilliseconds: 1,
        }),
    ).toThrow(RangeError);
    expect(
      () =>
        new SessionStore({
          absoluteLifetimeMilliseconds: 1,
          inactivityLifetimeMilliseconds: 1,
          transactionLifetimeMilliseconds: 1,
          maximumEntries: 0,
        }),
    ).toThrow(RangeError);
    const weak = new SessionStore({
      absoluteLifetimeMilliseconds: 1,
      inactivityLifetimeMilliseconds: 1,
      transactionLifetimeMilliseconds: 1,
      randomIdentifier: () => "weak",
    });
    expect(() =>
      weak.createTransaction(
        { state: "s", nonce: "n", codeVerifier: "v", returnTo: "/" },
        0,
      ),
    ).toThrow("unique session identifier");
  });
});
