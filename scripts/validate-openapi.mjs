import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { parse } from "yaml";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const openapiPath = path.join(
  repositoryRoot,
  "packages",
  "contracts",
  "openapi",
  "openapi.yaml",
);
const documentSchemaId = "https://portfolio.reactorfront.dev/contracts/openapi-document";
const openapi = parse(await readFile(openapiPath, "utf8"));

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
ajv.addSchema(openapi, documentSchemaId);

function formatErrors(errors) {
  return errors
    .map((error) => `${error.instancePath || "/"} ${error.message}`)
    .join("; ");
}

function compileReference(reference) {
  return ajv.compile({ $ref: `${documentSchemaId}${reference}` });
}

function resolveLocalReference(value) {
  if (!value?.$ref?.startsWith("#/")) {
    return value;
  }

  return value.$ref
    .slice(2)
    .split("/")
    .reduce((current, segment) => current[segment.replaceAll("~1", "/").replaceAll("~0", "~")], openapi);
}

function responseValidator(pathName, method, httpStatus) {
  const response = resolveLocalReference(
    openapi.paths[pathName][method].responses[String(httpStatus)],
  );
  const schema = response.content["application/problem+json"].schema;
  return schema.$ref ? compileReference(schema.$ref) : ajv.compile(schema);
}

function expectValid(validate, value, name) {
  if (!validate(value)) {
    throw new Error(`${name} should be valid: ${formatErrors(validate.errors)}`);
  }
}

function expectInvalid(validate, value, name) {
  if (validate(value)) {
    throw new Error(`${name} unexpectedly passed validation`);
  }
}

function withoutProperty(value, property) {
  const candidate = structuredClone(value);
  delete candidate[property];
  return candidate;
}

const documentStatus = compileReference("#/components/schemas/DocumentStatus");
const documentIdentity = {
  documentId: "22222222-2222-4222-8222-222222222222",
  jobId: "33333333-3333-4333-8333-333333333333",
  createdAt: "2026-07-18T07:00:00Z",
};
const validDocumentStatuses = [
  { ...documentIdentity, status: "accepted" },
  { ...documentIdentity, status: "queued" },
  {
    ...documentIdentity,
    status: "processing",
    startedAt: "2026-07-18T07:00:01Z",
  },
  {
    ...documentIdentity,
    status: "completed",
    startedAt: "2026-07-18T07:00:01Z",
    completedAt: "2026-07-18T07:00:02Z",
    classification: "invoice",
    confidence: 0.98,
    modelVersion: "document-type-v1",
  },
  {
    ...documentIdentity,
    status: "failed",
    completedAt: "2026-07-18T07:00:02Z",
    failureCode: "PDF_TEXT_EXTRACTION_FAILED",
  },
];

for (const status of validDocumentStatuses) {
  expectValid(documentStatus, status, `document status ${status.status}`);
}

const invalidDocumentStatuses = [
  {
    name: "completed document without classification",
    value: withoutProperty(validDocumentStatuses[3], "classification"),
  },
  {
    name: "accepted document with terminal result",
    value: {
      ...validDocumentStatuses[0],
      classification: "invoice",
      confidence: 0.98,
      modelVersion: "document-type-v1",
    },
  },
  {
    name: "failed document without failureCode",
    value: withoutProperty(validDocumentStatuses[4], "failureCode"),
  },
];

for (const invalidCase of invalidDocumentStatuses) {
  expectInvalid(documentStatus, invalidCase.value, invalidCase.name);
}

const correlationId = "11111111-1111-4111-8111-111111111111";
const problemContracts = [
  {
    pathName: "/api/v1/documents",
    method: "post",
    httpStatus: 400,
    code: "INVALID_DOCUMENT",
  },
  {
    pathName: "/api/v1/documents",
    method: "post",
    httpStatus: 413,
    code: "DOCUMENT_TOO_LARGE",
  },
  {
    pathName: "/api/v1/documents",
    method: "post",
    httpStatus: 415,
    code: "UNSUPPORTED_MEDIA_TYPE",
  },
  {
    pathName: "/api/v1/documents",
    method: "post",
    httpStatus: 503,
    code: "DEPENDENCY_UNAVAILABLE",
  },
  {
    pathName: "/api/v1/documents/{documentId}",
    method: "get",
    httpStatus: 404,
    code: "DOCUMENT_NOT_FOUND",
  },
  {
    pathName: "/api/v1/documents/{documentId}",
    method: "get",
    httpStatus: 503,
    code: "DEPENDENCY_UNAVAILABLE",
  },
  {
    pathName: "/ready",
    method: "get",
    httpStatus: 503,
    code: "DEPENDENCY_UNAVAILABLE",
  },
];

for (const contract of problemContracts) {
  const validate = responseValidator(
    contract.pathName,
    contract.method,
    contract.httpStatus,
  );
  const validProblem = {
    type: `urn:reactorfront:problem:${contract.code.toLowerCase().replaceAll("_", "-")}`,
    title: "Stable public problem",
    status: contract.httpStatus,
    code: contract.code,
    correlationId,
  };

  expectValid(validate, validProblem, `${contract.httpStatus} ${contract.code}`);
  expectInvalid(
    validate,
    { ...validProblem, status: contract.httpStatus === 503 ? 400 : 503 },
    `${contract.code} with mismatched body status`,
  );
  expectInvalid(
    validate,
    { ...validProblem, code: "ANY_ARBITRARY_CODE" },
    `${contract.code} with unknown code`,
  );
}

console.log(
  `Validated ${validDocumentStatuses.length} document states, ` +
    `${invalidDocumentStatuses.length} invalid state cases, and ` +
    `${problemContracts.length * 2} invalid problem cases.`,
);
