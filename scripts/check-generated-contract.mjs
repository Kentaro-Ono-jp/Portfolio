import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const generatedType = path.join(
  repositoryRoot,
  "packages",
  "contracts",
  "generated",
  "api.d.ts",
);
const before = await readFile(generatedType, "utf8");
const pnpmEntrypoint = process.env.npm_execpath;

if (!pnpmEntrypoint) {
  throw new Error("pnpm did not expose npm_execpath to the drift check.");
}

const generation = spawnSync(
  process.execPath,
  [pnpmEntrypoint, "contracts:generate"],
  { cwd: repositoryRoot, stdio: "inherit" },
);

if (generation.status !== 0) {
  throw new Error(`Contract generation failed with exit code ${generation.status}.`);
}

const after = await readFile(generatedType, "utf8");
if (before !== after) {
  throw new Error(
    "Generated API types had drifted and were refreshed. Review and commit the updated file.",
  );
}

console.log("Generated API types match the canonical OpenAPI contract.");
