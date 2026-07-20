import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const artifactRoot = path.resolve("artifacts/verification");

export default defineConfig({
  testDir: "tests/e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 180_000,
  expect: { timeout: 90_000 },
  outputDir: path.join(artifactRoot, "playwright"),
  reporter: [
    ["line"],
    [
      "html",
      {
        open: "never",
        outputFolder: path.join(artifactRoot, "playwright-report"),
      },
    ],
    ["junit", { outputFile: path.join(artifactRoot, "playwright-junit.xml") }],
  ],
  use: {
    baseURL: process.env.PORTFOLIO_E2E_BASE_URL ?? "http://127.0.0.1:53000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
