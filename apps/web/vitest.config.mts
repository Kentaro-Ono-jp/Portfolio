import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { tsconfigPaths: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary", "lcov"],
      reportsDirectory: "../../artifacts/verification/web-coverage",
      include: [
        "src/app/api/**/*.ts",
        "src/components/**/*.tsx",
        "src/lib/**/*.ts",
      ],
      exclude: ["**/*.test.{ts,tsx}"],
      thresholds: {
        branches: 90,
        functions: 90,
        lines: 90,
        statements: 90,
      },
    },
  },
});
