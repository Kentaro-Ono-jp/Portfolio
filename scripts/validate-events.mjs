import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const schemaDirectory = path.join(repositoryRoot, "packages", "contracts", "events");
const exampleDirectory = path.join(
  repositoryRoot,
  "packages",
  "contracts",
  "examples",
  "events",
);
const schemaBase = "https://portfolio.reactorfront.dev/contracts/events";

async function readJsonFiles(directory) {
  const filenames = (await readdir(directory))
    .filter((filename) => filename.endsWith(".json"))
    .sort();

  return Promise.all(
    filenames.map(async (filename) => ({
      filename,
      value: JSON.parse(await readFile(path.join(directory, filename), "utf8")),
    })),
  );
}

function formatErrors(errors) {
  return errors
    .map((error) => `${error.instancePath || "/"} ${error.message}`)
    .join("; ");
}

const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);

for (const { value: schema } of await readJsonFiles(schemaDirectory)) {
  ajv.addSchema(schema);
}

const examples = await readJsonFiles(exampleDirectory);
for (const { filename, value: event } of examples) {
  const schemaId = `${schemaBase}/${event.eventType}.schema.json`;
  const validate = ajv.getSchema(schemaId);

  if (!validate) {
    throw new Error(`${filename}: no schema registered for ${event.eventType}`);
  }

  if (!validate(event)) {
    throw new Error(`${filename}: ${formatErrors(validate.errors)}`);
  }
}

const completed = examples.find(
  ({ value }) => value.eventType === "document.processing.completed.v1",
);
if (!completed) {
  throw new Error("A completed event example is required for negative validation.");
}

const completedSchema = ajv.getSchema(
  `${schemaBase}/document.processing.completed.v1.schema.json`,
);
const invalidCases = [
  {
    name: "missing required jobId",
    mutate(event) {
      delete event.jobId;
    },
  },
  {
    name: "unknown property",
    mutate(event) {
      event.rawException = "must not cross the public event boundary";
    },
  },
  {
    name: "invalid source digest",
    mutate(event) {
      event.sourceSha256 = "not-a-sha256";
    },
  },
];

for (const invalidCase of invalidCases) {
  const candidate = structuredClone(completed.value);
  invalidCase.mutate(candidate);
  if (completedSchema(candidate)) {
    throw new Error(`Negative case unexpectedly passed: ${invalidCase.name}`);
  }
}

console.log(
  `Validated ${examples.length} event examples and ${invalidCases.length} rejection cases.`,
);
