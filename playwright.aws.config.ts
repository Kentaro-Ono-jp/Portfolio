import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PORTFOLIO_AWS_SMOKE_BASE_URL;

if (baseURL === undefined || !baseURL.startsWith("https://")) {
  throw new Error("PORTFOLIO_AWS_SMOKE_BASE_URL must be an HTTPS endpoint.");
}

export default defineConfig({
  testDir: "tests/aws",
  testMatch: "lifecycle-smoke.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 360_000,
  expect: { timeout: 180_000 },
  outputDir: path.resolve("artifacts/private-verification/aws-smoke"),
  reporter: [["line"]],
  use: {
    baseURL,
    trace: "off",
    screenshot: "off",
    video: "off",
    ...devices["Desktop Chrome"],
  },
});
