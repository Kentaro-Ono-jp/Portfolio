import * as oidc from "openid-client";
import { z } from "zod";

import type { OidcTransaction, SessionTokens } from "@/lib/auth-session-store";
import type { ServerConfig } from "@/lib/server-config";

const MAX_DISCOVERY_BYTES = 64 * 1024;
const discoverySchema = z
  .object({
    issuer: z.url(),
    authorization_endpoint: z.url(),
    token_endpoint: z.url(),
    jwks_uri: z.url(),
    response_types_supported: z.array(z.string()),
    grant_types_supported: z.array(z.string()).optional(),
    code_challenge_methods_supported: z.array(z.string()).optional(),
    id_token_signing_alg_values_supported: z.array(z.string()),
  })
  .passthrough();

export class OidcBoundaryError extends Error {
  constructor(cause?: unknown) {
    super(
      "The sign-in boundary is temporarily unavailable.",
      cause === undefined ? undefined : { cause },
    );
    this.name = "OidcBoundaryError";
  }
}

export interface AuthorizationStart {
  authorizationUrl: URL;
  transaction: OidcTransaction;
}

export interface OidcResult {
  subject: string;
  tokens: SessionTokens;
}

export interface OidcDependencies {
  fetch: typeof fetch;
  now: () => number;
}

const defaultDependencies: OidcDependencies = {
  fetch: globalThis.fetch,
  now: Date.now,
};

function sameEndpointPath(discovered: string, configured: string): boolean {
  const discoveredUrl = new URL(discovered);
  const configuredUrl = new URL(configured);
  return (
    discoveredUrl.pathname === configuredUrl.pathname &&
    discoveredUrl.search === configuredUrl.search
  );
}

function sameEndpoint(discovered: string, configured: string): boolean {
  return new URL(discovered).href === new URL(configured).href;
}

async function loadConfiguration(
  settings: ServerConfig,
  overrides: Partial<OidcDependencies> = {},
): Promise<oidc.Configuration> {
  const dependencies = { ...defaultDependencies, ...overrides };
  let response: Response;
  try {
    response = await dependencies.fetch(settings.oidcDiscoveryUrl, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(settings.timeoutMilliseconds),
      cache: "no-store",
    });
  } catch (error) {
    throw new OidcBoundaryError(error);
  }
  if (!response.ok) {
    throw new OidcBoundaryError();
  }
  const declaredLength = Number(response.headers.get("Content-Length"));
  if (Number.isFinite(declaredLength) && declaredLength > MAX_DISCOVERY_BYTES) {
    throw new OidcBoundaryError();
  }

  let text: string;
  try {
    text = await response.text();
  } catch (error) {
    throw new OidcBoundaryError(error);
  }
  if (Buffer.byteLength(text, "utf8") > MAX_DISCOVERY_BYTES) {
    throw new OidcBoundaryError();
  }

  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    throw new OidcBoundaryError(error);
  }
  const parsed = discoverySchema.safeParse(payload);
  if (!parsed.success || parsed.data.issuer !== settings.oidcIssuer) {
    throw new OidcBoundaryError();
  }
  if (
    !sameEndpoint(
      parsed.data.authorization_endpoint,
      settings.oidcAuthorizationUrl,
    ) ||
    !sameEndpointPath(parsed.data.token_endpoint, settings.oidcTokenUrl) ||
    !sameEndpointPath(parsed.data.jwks_uri, settings.oidcJwksUrl) ||
    !parsed.data.response_types_supported.includes("code") ||
    (parsed.data.grant_types_supported !== undefined &&
      !parsed.data.grant_types_supported.includes("authorization_code")) ||
    (parsed.data.code_challenge_methods_supported !== undefined &&
      !parsed.data.code_challenge_methods_supported.includes("S256")) ||
    !parsed.data.id_token_signing_alg_values_supported.includes("RS256")
  ) {
    throw new OidcBoundaryError();
  }

  const serverMetadata: ConstructorParameters<typeof oidc.Configuration>[0] = {
    issuer: parsed.data.issuer,
    authorization_endpoint: settings.oidcAuthorizationUrl,
    token_endpoint: settings.oidcTokenUrl,
    jwks_uri: settings.oidcJwksUrl,
    response_types_supported: parsed.data.response_types_supported,
    id_token_signing_alg_values_supported:
      parsed.data.id_token_signing_alg_values_supported,
    ...(parsed.data.grant_types_supported === undefined
      ? {}
      : { grant_types_supported: parsed.data.grant_types_supported }),
    ...(parsed.data.code_challenge_methods_supported === undefined
      ? {}
      : {
          code_challenge_methods_supported:
            parsed.data.code_challenge_methods_supported,
        }),
  };
  const clientMetadata = {
    redirect_uris: [settings.redirectUri],
    response_types: ["code"],
    token_endpoint_auth_method:
      settings.oidcClientSecret === undefined ? "none" : "client_secret_post",
    ...(settings.oidcClientSecret === undefined
      ? {}
      : { client_secret: settings.oidcClientSecret }),
  };
  const clientAuthentication =
    settings.oidcClientSecret === undefined
      ? oidc.None()
      : oidc.ClientSecretPost(settings.oidcClientSecret);
  const configuration = new oidc.Configuration(
    serverMetadata,
    settings.oidcClientId,
    clientMetadata,
    clientAuthentication,
  );
  configuration.timeout = Math.ceil(settings.timeoutMilliseconds / 1_000);
  if (settings.allowInsecureLoopback) {
    oidc.allowInsecureRequests(configuration);
  }
  return configuration;
}

function requireTokenResult(
  tokenResponse: Awaited<ReturnType<typeof oidc.authorizationCodeGrant>>,
  now: number,
): OidcResult {
  const claims = tokenResponse.claims();
  const expiresIn = tokenResponse.expiresIn();
  if (
    claims === undefined ||
    typeof claims.sub !== "string" ||
    claims.sub.length === 0 ||
    claims.sub.length > 255 ||
    typeof tokenResponse.access_token !== "string" ||
    tokenResponse.access_token.length === 0 ||
    expiresIn === undefined ||
    expiresIn <= 0
  ) {
    throw new OidcBoundaryError();
  }
  return {
    subject: claims.sub,
    tokens: {
      accessToken: tokenResponse.access_token,
      accessTokenExpiresAt: now + expiresIn * 1_000,
      ...(typeof tokenResponse.refresh_token === "string"
        ? { refreshToken: tokenResponse.refresh_token }
        : {}),
      ...(typeof tokenResponse.id_token === "string"
        ? { idToken: tokenResponse.id_token }
        : {}),
    },
  };
}

export async function beginAuthorization(
  settings: ServerConfig,
  overrides: Partial<OidcDependencies> = {},
): Promise<AuthorizationStart> {
  try {
    const configuration = await loadConfiguration(settings, overrides);
    const codeVerifier = oidc.randomPKCECodeVerifier();
    const state = oidc.randomState();
    const nonce = oidc.randomNonce();
    const authorizationUrl = oidc.buildAuthorizationUrl(configuration, {
      redirect_uri: settings.redirectUri,
      response_type: "code",
      scope: settings.oidcScopes,
      ...(settings.oidcResource === undefined
        ? {}
        : { resource: settings.oidcResource }),
      state,
      nonce,
      code_challenge: await oidc.calculatePKCECodeChallenge(codeVerifier),
      code_challenge_method: "S256",
    });
    return {
      authorizationUrl,
      transaction: { state, nonce, codeVerifier, returnTo: "/" },
    };
  } catch (error) {
    if (error instanceof OidcBoundaryError) {
      throw error;
    }
    throw new OidcBoundaryError(error);
  }
}

export async function completeAuthorization(
  settings: ServerConfig,
  callbackRequestUrl: string,
  transaction: OidcTransaction,
  overrides: Partial<OidcDependencies> = {},
): Promise<OidcResult> {
  const dependencies = { ...defaultDependencies, ...overrides };
  try {
    const configuration = await loadConfiguration(settings, overrides);
    const trustedCallback = new URL(settings.redirectUri);
    trustedCallback.search = new URL(callbackRequestUrl).search;
    const tokens = await oidc.authorizationCodeGrant(
      configuration,
      trustedCallback,
      {
        expectedState: transaction.state,
        expectedNonce: transaction.nonce,
        pkceCodeVerifier: transaction.codeVerifier,
      },
    );
    return requireTokenResult(tokens, dependencies.now());
  } catch (error) {
    if (error instanceof OidcBoundaryError) {
      throw error;
    }
    throw new OidcBoundaryError(error);
  }
}

export async function refreshAuthorization(
  settings: ServerConfig,
  refreshToken: string,
  subject: string,
  previousIdToken: string | undefined,
  overrides: Partial<OidcDependencies> = {},
): Promise<SessionTokens> {
  const dependencies = { ...defaultDependencies, ...overrides };
  try {
    const configuration = await loadConfiguration(settings, overrides);
    const tokens = await oidc.refreshTokenGrant(configuration, refreshToken);
    const expiresIn = tokens.expiresIn();
    if (
      typeof tokens.access_token !== "string" ||
      tokens.access_token.length === 0 ||
      expiresIn === undefined ||
      expiresIn <= 0
    ) {
      throw new OidcBoundaryError();
    }
    const claims = tokens.claims();
    if (claims !== undefined && claims.sub !== subject) {
      throw new OidcBoundaryError();
    }
    return {
      accessToken: tokens.access_token,
      accessTokenExpiresAt: dependencies.now() + expiresIn * 1_000,
      refreshToken:
        typeof tokens.refresh_token === "string"
          ? tokens.refresh_token
          : refreshToken,
      ...(typeof tokens.id_token === "string"
        ? { idToken: tokens.id_token }
        : previousIdToken === undefined
          ? {}
          : { idToken: previousIdToken }),
    };
  } catch (error) {
    if (error instanceof OidcBoundaryError) {
      throw error;
    }
    throw new OidcBoundaryError(error);
  }
}
