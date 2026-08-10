import { z } from "zod";

const DEFAULT_TIMEOUT_MILLISECONDS = 8_000;
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]"]);

const httpUrlSchema = z.url().refine((value) => {
  try {
    const parsed = new URL(value);
    return (
      (parsed.protocol === "http:" || parsed.protocol === "https:") &&
      parsed.username === "" &&
      parsed.password === "" &&
      parsed.hash === ""
    );
  } catch {
    return false;
  }
});

const booleanString = z
  .enum(["true", "false"])
  .transform((value) => value === "true");

const serverConfigSchema = z.strictObject({
  PORTFOLIO_API_BASE_URL: httpUrlSchema,
  PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS: z.coerce
    .number()
    .int()
    .min(100)
    .max(30_000)
    .default(DEFAULT_TIMEOUT_MILLISECONDS),
  PORTFOLIO_WEB_PUBLIC_BASE_URL: httpUrlSchema,
  PORTFOLIO_WEB_OIDC_ISSUER: httpUrlSchema,
  PORTFOLIO_WEB_OIDC_AUTHORIZATION_URL: httpUrlSchema,
  PORTFOLIO_WEB_OIDC_DISCOVERY_URL: httpUrlSchema,
  PORTFOLIO_WEB_OIDC_TOKEN_URL: httpUrlSchema,
  PORTFOLIO_WEB_OIDC_JWKS_URL: httpUrlSchema,
  PORTFOLIO_WEB_OIDC_CLIENT_ID: z.string().trim().min(1).max(255),
  PORTFOLIO_WEB_OIDC_CLIENT_SECRET: z.string().min(1).max(4096).optional(),
  PORTFOLIO_WEB_OIDC_SCOPES: z
    .string()
    .trim()
    .min(1)
    .default("openid groups offline_access"),
  PORTFOLIO_WEB_OIDC_RESOURCE: httpUrlSchema.optional(),
  PORTFOLIO_WEB_OIDC_ALLOW_INSECURE_LOOPBACK: booleanString.default(false),
  PORTFOLIO_WEB_SESSION_ABSOLUTE_SECONDS: z.coerce
    .number()
    .int()
    .min(300)
    .max(86_400)
    .default(28_800),
  PORTFOLIO_WEB_SESSION_INACTIVITY_SECONDS: z.coerce
    .number()
    .int()
    .min(60)
    .max(14_400)
    .default(1_800),
  PORTFOLIO_WEB_OIDC_TRANSACTION_SECONDS: z.coerce
    .number()
    .int()
    .min(60)
    .max(600)
    .default(300),
  PORTFOLIO_WEB_TOKEN_REFRESH_LEEWAY_SECONDS: z.coerce
    .number()
    .int()
    .min(5)
    .max(300)
    .default(30),
});

export interface ServerConfig {
  apiBaseUrl: string;
  timeoutMilliseconds: number;
  publicBaseUrl: string;
  oidcIssuer: string;
  oidcAuthorizationUrl: string;
  oidcDiscoveryUrl: string;
  oidcTokenUrl: string;
  oidcJwksUrl: string;
  oidcClientId: string;
  oidcClientSecret?: string;
  oidcScopes: string;
  oidcResource?: string;
  allowInsecureLoopback: boolean;
  sessionAbsoluteSeconds: number;
  sessionInactivitySeconds: number;
  oidcTransactionSeconds: number;
  tokenRefreshLeewaySeconds: number;
  secureCookies: boolean;
  redirectUri: string;
}

export class InvalidServerConfigurationError extends Error {
  constructor() {
    super("Web server configuration is unavailable.");
    this.name = "InvalidServerConfigurationError";
  }
}

function normalizedUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

function isLoopbackUrl(value: string): boolean {
  return LOOPBACK_HOSTS.has(new URL(value).hostname);
}

function requireSafeOidcTransport(
  values: z.infer<typeof serverConfigSchema>,
): void {
  const publicBase = new URL(values.PORTFOLIO_WEB_PUBLIC_BASE_URL);
  const issuer = new URL(values.PORTFOLIO_WEB_OIDC_ISSUER);
  const oidcUrls = [
    issuer,
    new URL(values.PORTFOLIO_WEB_OIDC_AUTHORIZATION_URL),
    new URL(values.PORTFOLIO_WEB_OIDC_DISCOVERY_URL),
    new URL(values.PORTFOLIO_WEB_OIDC_TOKEN_URL),
    new URL(values.PORTFOLIO_WEB_OIDC_JWKS_URL),
    ...(values.PORTFOLIO_WEB_OIDC_RESOURCE === undefined
      ? []
      : [new URL(values.PORTFOLIO_WEB_OIDC_RESOURCE)]),
  ];

  if (values.PORTFOLIO_WEB_OIDC_ALLOW_INSECURE_LOOPBACK) {
    if (
      publicBase.protocol !== "http:" ||
      issuer.protocol !== "http:" ||
      !isLoopbackUrl(publicBase.href) ||
      !isLoopbackUrl(issuer.href) ||
      !isLoopbackUrl(values.PORTFOLIO_WEB_OIDC_AUTHORIZATION_URL)
    ) {
      throw new InvalidServerConfigurationError();
    }
    return;
  }

  if (
    publicBase.protocol !== "https:" ||
    oidcUrls.some((url) => url.protocol !== "https:")
  ) {
    throw new InvalidServerConfigurationError();
  }
}

export function readServerConfig(
  environment: Readonly<Record<string, string | undefined>> = process.env,
): ServerConfig {
  const parsed = serverConfigSchema.safeParse({
    PORTFOLIO_API_BASE_URL: environment.PORTFOLIO_API_BASE_URL,
    PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS:
      environment.PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS,
    PORTFOLIO_WEB_PUBLIC_BASE_URL: environment.PORTFOLIO_WEB_PUBLIC_BASE_URL,
    PORTFOLIO_WEB_OIDC_ISSUER: environment.PORTFOLIO_WEB_OIDC_ISSUER,
    PORTFOLIO_WEB_OIDC_AUTHORIZATION_URL:
      environment.PORTFOLIO_WEB_OIDC_AUTHORIZATION_URL,
    PORTFOLIO_WEB_OIDC_DISCOVERY_URL:
      environment.PORTFOLIO_WEB_OIDC_DISCOVERY_URL,
    PORTFOLIO_WEB_OIDC_TOKEN_URL: environment.PORTFOLIO_WEB_OIDC_TOKEN_URL,
    PORTFOLIO_WEB_OIDC_JWKS_URL: environment.PORTFOLIO_WEB_OIDC_JWKS_URL,
    PORTFOLIO_WEB_OIDC_CLIENT_ID: environment.PORTFOLIO_WEB_OIDC_CLIENT_ID,
    PORTFOLIO_WEB_OIDC_CLIENT_SECRET:
      environment.PORTFOLIO_WEB_OIDC_CLIENT_SECRET,
    PORTFOLIO_WEB_OIDC_SCOPES: environment.PORTFOLIO_WEB_OIDC_SCOPES,
    PORTFOLIO_WEB_OIDC_RESOURCE: environment.PORTFOLIO_WEB_OIDC_RESOURCE,
    PORTFOLIO_WEB_OIDC_ALLOW_INSECURE_LOOPBACK:
      environment.PORTFOLIO_WEB_OIDC_ALLOW_INSECURE_LOOPBACK,
    PORTFOLIO_WEB_SESSION_ABSOLUTE_SECONDS:
      environment.PORTFOLIO_WEB_SESSION_ABSOLUTE_SECONDS,
    PORTFOLIO_WEB_SESSION_INACTIVITY_SECONDS:
      environment.PORTFOLIO_WEB_SESSION_INACTIVITY_SECONDS,
    PORTFOLIO_WEB_OIDC_TRANSACTION_SECONDS:
      environment.PORTFOLIO_WEB_OIDC_TRANSACTION_SECONDS,
    PORTFOLIO_WEB_TOKEN_REFRESH_LEEWAY_SECONDS:
      environment.PORTFOLIO_WEB_TOKEN_REFRESH_LEEWAY_SECONDS,
  });
  if (!parsed.success) {
    throw new InvalidServerConfigurationError();
  }

  requireSafeOidcTransport(parsed.data);
  const scopes = new Set(parsed.data.PORTFOLIO_WEB_OIDC_SCOPES.split(/\s+/));
  if (!scopes.has("openid")) {
    throw new InvalidServerConfigurationError();
  }

  const publicBaseUrl = normalizedUrl(
    parsed.data.PORTFOLIO_WEB_PUBLIC_BASE_URL,
  );
  const clientSecret = parsed.data.PORTFOLIO_WEB_OIDC_CLIENT_SECRET;
  return {
    apiBaseUrl: normalizedUrl(parsed.data.PORTFOLIO_API_BASE_URL),
    timeoutMilliseconds: parsed.data.PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS,
    publicBaseUrl,
    oidcIssuer: normalizedUrl(parsed.data.PORTFOLIO_WEB_OIDC_ISSUER),
    oidcAuthorizationUrl: parsed.data.PORTFOLIO_WEB_OIDC_AUTHORIZATION_URL,
    oidcDiscoveryUrl: parsed.data.PORTFOLIO_WEB_OIDC_DISCOVERY_URL,
    oidcTokenUrl: parsed.data.PORTFOLIO_WEB_OIDC_TOKEN_URL,
    oidcJwksUrl: parsed.data.PORTFOLIO_WEB_OIDC_JWKS_URL,
    oidcClientId: parsed.data.PORTFOLIO_WEB_OIDC_CLIENT_ID,
    ...(clientSecret === undefined ? {} : { oidcClientSecret: clientSecret }),
    oidcScopes: parsed.data.PORTFOLIO_WEB_OIDC_SCOPES,
    ...(parsed.data.PORTFOLIO_WEB_OIDC_RESOURCE === undefined
      ? {}
      : {
          oidcResource: normalizedUrl(parsed.data.PORTFOLIO_WEB_OIDC_RESOURCE),
        }),
    allowInsecureLoopback:
      parsed.data.PORTFOLIO_WEB_OIDC_ALLOW_INSECURE_LOOPBACK,
    sessionAbsoluteSeconds: parsed.data.PORTFOLIO_WEB_SESSION_ABSOLUTE_SECONDS,
    sessionInactivitySeconds:
      parsed.data.PORTFOLIO_WEB_SESSION_INACTIVITY_SECONDS,
    oidcTransactionSeconds: parsed.data.PORTFOLIO_WEB_OIDC_TRANSACTION_SECONDS,
    tokenRefreshLeewaySeconds:
      parsed.data.PORTFOLIO_WEB_TOKEN_REFRESH_LEEWAY_SECONDS,
    secureCookies: new URL(publicBaseUrl).protocol === "https:",
    redirectUri: `${publicBaseUrl}/api/auth/callback`,
  };
}
