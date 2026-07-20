import { z } from "zod";

const DEFAULT_TIMEOUT_MILLISECONDS = 8_000;
const httpUrlSchema = z.url().refine((value) => {
  try {
    const protocol = new URL(value).protocol;
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
});

const serverConfigSchema = z.strictObject({
  PORTFOLIO_API_BASE_URL: httpUrlSchema,
  PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS: z.coerce
    .number()
    .int()
    .min(100)
    .max(30_000)
    .default(DEFAULT_TIMEOUT_MILLISECONDS),
});

export interface ServerConfig {
  apiBaseUrl: string;
  timeoutMilliseconds: number;
}

export class InvalidServerConfigurationError extends Error {
  constructor() {
    super("Web upstream configuration is unavailable.");
    this.name = "InvalidServerConfigurationError";
  }
}

export function readServerConfig(
  environment: Readonly<Record<string, string | undefined>> = process.env,
): ServerConfig {
  const parsed = serverConfigSchema.safeParse({
    PORTFOLIO_API_BASE_URL: environment.PORTFOLIO_API_BASE_URL,
    PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS:
      environment.PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS,
  });
  if (!parsed.success) {
    throw new InvalidServerConfigurationError();
  }

  return {
    apiBaseUrl: parsed.data.PORTFOLIO_API_BASE_URL.replace(/\/+$/, ""),
    timeoutMilliseconds: parsed.data.PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS,
  };
}
