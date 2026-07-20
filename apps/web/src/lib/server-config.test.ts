import { describe, expect, it } from "vitest";

import {
  InvalidServerConfigurationError,
  readServerConfig,
} from "@/lib/server-config";

describe("readServerConfig", () => {
  it("normalizes a valid runtime URL and default timeout", () => {
    expect(
      readServerConfig({
        PATH: "a normal process environment entry",
        PORTFOLIO_API_BASE_URL: "http://api:8000/",
      }),
    ).toEqual({ apiBaseUrl: "http://api:8000", timeoutMilliseconds: 8_000 });
  });

  it("accepts a bounded explicit timeout", () => {
    expect(
      readServerConfig({
        PORTFOLIO_API_BASE_URL: "https://api.example.test/base",
        PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS: "1500",
      }),
    ).toEqual({
      apiBaseUrl: "https://api.example.test/base",
      timeoutMilliseconds: 1_500,
    });
  });

  it("rejects missing, malformed, and unsafe timeout configuration", () => {
    for (const environment of [
      {},
      { PORTFOLIO_API_BASE_URL: "not a URL" },
      { PORTFOLIO_API_BASE_URL: "file:///private/api.sock" },
      {
        PORTFOLIO_API_BASE_URL: "http://api:8000",
        PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS: "0",
      },
    ]) {
      expect(() => readServerConfig(environment)).toThrow(
        InvalidServerConfigurationError,
      );
    }
  });
});
