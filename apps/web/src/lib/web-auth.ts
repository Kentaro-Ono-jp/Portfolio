import { SessionStore, type WebSession } from "@/lib/auth-session-store";
import {
  beginAuthorization,
  completeAuthorization,
  OidcBoundaryError,
  refreshAuthorization,
} from "@/lib/oidc";
import { readServerConfig, type ServerConfig } from "@/lib/server-config";

export const SESSION_COOKIE = "portfolio_session";
export const TRANSACTION_COOKIE = "portfolio_oidc_transaction";
export const CSRF_HEADER = "X-CSRF-Token";

let sharedStore: SessionStore | undefined;
let sharedStoreKey: string | undefined;

export class WebAuthenticationError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "WebAuthenticationError";
  }
}

interface WebAuthDependencies {
  settings: ServerConfig;
  store: SessionStore;
  now: () => number;
  begin: typeof beginAuthorization;
  complete: typeof completeAuthorization;
  refresh: typeof refreshAuthorization;
}

export interface WebAuthOverrides {
  environment?: Readonly<Record<string, string | undefined>>;
  store?: SessionStore;
  now?: () => number;
  begin?: typeof beginAuthorization;
  complete?: typeof completeAuthorization;
  refresh?: typeof refreshAuthorization;
}

function sessionStore(settings: ServerConfig): SessionStore {
  const key = [
    settings.sessionAbsoluteSeconds,
    settings.sessionInactivitySeconds,
    settings.oidcTransactionSeconds,
  ].join(":");
  if (sharedStore === undefined || sharedStoreKey !== key) {
    sharedStore = new SessionStore({
      absoluteLifetimeMilliseconds: settings.sessionAbsoluteSeconds * 1_000,
      inactivityLifetimeMilliseconds: settings.sessionInactivitySeconds * 1_000,
      transactionLifetimeMilliseconds: settings.oidcTransactionSeconds * 1_000,
    });
    sharedStoreKey = key;
  }
  return sharedStore;
}

function dependencies(overrides: WebAuthOverrides): WebAuthDependencies {
  const settings = readServerConfig(overrides.environment ?? process.env);
  return {
    settings,
    store: overrides.store ?? sessionStore(settings),
    now: overrides.now ?? Date.now,
    begin: overrides.begin ?? beginAuthorization,
    complete: overrides.complete ?? completeAuthorization,
    refresh: overrides.refresh ?? refreshAuthorization,
  };
}

export function cookieValue(
  cookieHeader: string | null,
  name: string,
): string | undefined {
  if (cookieHeader === null) {
    return undefined;
  }
  for (const part of cookieHeader.split(";")) {
    const [candidate, ...valueParts] = part.trim().split("=");
    if (candidate === name) {
      const value = valueParts.join("=");
      return value === "" ? undefined : value;
    }
  }
  return undefined;
}

function cookie(
  name: string,
  value: string,
  settings: ServerConfig,
  maximumAge: number,
  path: string,
): string {
  return [
    `${name}=${value}`,
    `Path=${path}`,
    `Max-Age=${maximumAge}`,
    "HttpOnly",
    "SameSite=Lax",
    ...(settings.secureCookies ? ["Secure"] : []),
  ].join("; ");
}

function clearCookie(
  name: string,
  settings: ServerConfig,
  path: string,
): string {
  return cookie(name, "", settings, 0, path);
}

export function sanitizedAuthProblem(error: WebAuthenticationError): Response {
  const correlationId = crypto.randomUUID();
  return Response.json(
    {
      type: `/problems/${error.code.toLowerCase().replaceAll("_", "-")}`,
      title: error.message,
      status: error.status,
      code: error.code,
      detail:
        error.status === 401
          ? "Sign in again before retrying this request."
          : "Please wait a moment and try again.",
      correlationId,
    },
    {
      status: error.status,
      headers: {
        "Content-Type": "application/problem+json",
        "X-Correlation-ID": correlationId,
      },
    },
  );
}

export async function startSignIn(
  overrides: WebAuthOverrides = {},
): Promise<Response> {
  const resolved = dependencies(overrides);
  try {
    const started = await resolved.begin(resolved.settings);
    const transactionId = resolved.store.createTransaction(
      started.transaction,
      resolved.now(),
    );
    return new Response(null, {
      status: 302,
      headers: {
        Location: started.authorizationUrl.href,
        "Cache-Control": "no-store",
        "Set-Cookie": cookie(
          TRANSACTION_COOKIE,
          transactionId,
          resolved.settings,
          resolved.settings.oidcTransactionSeconds,
          "/api/auth/callback",
        ),
      },
    });
  } catch (error) {
    if (error instanceof OidcBoundaryError) {
      throw new WebAuthenticationError(
        503,
        "WEB_IDENTITY_UNAVAILABLE",
        "The identity service is temporarily unavailable.",
      );
    }
    throw error;
  }
}

export async function finishSignIn(
  request: Request,
  overrides: WebAuthOverrides = {},
): Promise<Response> {
  const resolved = dependencies(overrides);
  const transactionId = cookieValue(
    request.headers.get("Cookie"),
    TRANSACTION_COOKIE,
  );
  const transaction = resolved.store.consumeTransaction(
    transactionId,
    resolved.now(),
  );
  if (transaction === null) {
    throw new WebAuthenticationError(
      401,
      "WEB_AUTHENTICATION_FAILED",
      "The sign-in attempt is invalid or expired.",
    );
  }

  try {
    const result = await resolved.complete(
      resolved.settings,
      request.url,
      transaction,
    );
    const session = resolved.store.createSession(
      result.tokens,
      result.subject,
      resolved.now(),
    );
    const response = new Response(null, {
      status: 303,
      headers: {
        Location: transaction.returnTo,
        "Cache-Control": "no-store",
        "Set-Cookie": cookie(
          SESSION_COOKIE,
          session.id,
          resolved.settings,
          resolved.settings.sessionAbsoluteSeconds,
          "/",
        ),
      },
    });
    response.headers.append(
      "Set-Cookie",
      clearCookie(TRANSACTION_COOKIE, resolved.settings, "/api/auth/callback"),
    );
    return response;
  } catch (error) {
    if (error instanceof OidcBoundaryError) {
      throw new WebAuthenticationError(
        401,
        "WEB_AUTHENTICATION_FAILED",
        "The sign-in attempt could not be validated.",
      );
    }
    throw error;
  }
}

export async function requireWebSession(
  request: Request,
  overrides: WebAuthOverrides = {},
): Promise<WebSession> {
  const resolved = dependencies(overrides);
  const sessionId = cookieValue(request.headers.get("Cookie"), SESSION_COOKIE);
  const now = resolved.now();
  const session = resolved.store.getSession(sessionId, now);
  if (session === null) {
    throw new WebAuthenticationError(
      401,
      "WEB_SESSION_REQUIRED",
      "A valid browser session is required.",
    );
  }
  if (
    session.accessTokenExpiresAt >
    now + resolved.settings.tokenRefreshLeewaySeconds * 1_000
  ) {
    return session;
  }
  if (session.refreshToken === undefined) {
    resolved.store.deleteSession(session.id);
    throw new WebAuthenticationError(
      401,
      "WEB_SESSION_EXPIRED",
      "The browser session has expired.",
    );
  }
  try {
    const tokens = await resolved.refresh(
      resolved.settings,
      session.refreshToken,
      session.subject,
      session.idToken,
    );
    const refreshed = resolved.store.replaceTokens(session.id, tokens, now);
    if (refreshed === null) {
      throw new WebAuthenticationError(
        401,
        "WEB_SESSION_EXPIRED",
        "The browser session has expired.",
      );
    }
    return refreshed;
  } catch (error) {
    if (error instanceof WebAuthenticationError) {
      throw error;
    }
    if (session.accessTokenExpiresAt > now) {
      return session;
    }
    resolved.store.deleteSession(session.id);
    throw new WebAuthenticationError(
      401,
      "WEB_SESSION_EXPIRED",
      "The browser session has expired.",
    );
  }
}

export function requireCsrf(
  request: Request,
  session: WebSession,
  overrides: WebAuthOverrides = {},
): void {
  const resolved = dependencies(overrides);
  if (!resolved.store.csrfMatches(session, request.headers.get(CSRF_HEADER))) {
    throw new WebAuthenticationError(
      403,
      "WEB_CSRF_REJECTED",
      "The request could not be verified.",
    );
  }
}

export function currentBrowserSession(
  sessionId: string | undefined,
  overrides: WebAuthOverrides = {},
): Pick<WebSession, "csrfToken" | "absoluteExpiresAt"> | null {
  const resolved = dependencies(overrides);
  const session = resolved.store.getSession(sessionId, resolved.now(), false);
  return session === null
    ? null
    : {
        csrfToken: session.csrfToken,
        absoluteExpiresAt: session.absoluteExpiresAt,
      };
}

export function signOut(
  request: Request,
  overrides: WebAuthOverrides = {},
): Response {
  const resolved = dependencies(overrides);
  const sessionId = cookieValue(request.headers.get("Cookie"), SESSION_COOKIE);
  const session = resolved.store.getSession(sessionId, resolved.now(), false);
  if (session === null) {
    throw new WebAuthenticationError(
      401,
      "WEB_SESSION_REQUIRED",
      "A valid browser session is required.",
    );
  }
  if (!resolved.store.csrfMatches(session, request.headers.get(CSRF_HEADER))) {
    throw new WebAuthenticationError(
      403,
      "WEB_CSRF_REJECTED",
      "The request could not be verified.",
    );
  }
  resolved.store.deleteSession(session.id);
  return new Response(null, {
    status: 204,
    headers: {
      "Cache-Control": "no-store",
      "Set-Cookie": clearCookie(SESSION_COOKIE, resolved.settings, "/"),
    },
  });
}
