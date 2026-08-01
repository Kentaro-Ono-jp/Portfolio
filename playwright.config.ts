import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

const publicArtifactRoot = path.resolve("artifacts/verification");
const privateArtifactRoot = path.resolve("artifacts/private-verification");

export default defineConfig({
  testDir: "tests/e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 180_000,
  expect: { timeout: 90_000 },
  outputDir: path.join(privateArtifactRoot, "playwright"),
  reporter: [
    ["line"],
    [
      "html",
      {
        open: "never",
        outputFolder: path.join(privateArtifactRoot, "playwright-report"),
      },
    ],
    [
      "junit",
      { outputFile: path.join(publicArtifactRoot, "playwright-junit.xml") },
    ],
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
