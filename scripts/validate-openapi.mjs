import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { parse } from "yaml";

const repositoryRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const openapiPath = path.join(
  repositoryRoot,
  "packages",
  "contracts",
  "openapi",
  "openapi.yaml",
);
const documentSchemaId =
  "https://portfolio.reactorfront.dev/contracts/openapi-document";
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
    .reduce(
      (current, segment) =>
        current[segment.replaceAll("~1", "/").replaceAll("~0", "~")],
      openapi,
    );
}

function responseValidator(pathName, method, httpStatus) {
  const response = resolveLocalReference(
    openapi.paths[pathName][method].responses[String(httpStatus)],
  );
  const schema = response.content["application/problem+json"].schema;
  return schema.$ref ? compileReference(schema.$ref) : ajv.compile(schema);
}

function componentResponseValidator(responseName) {
  const response = openapi.components.responses[responseName];
  const schema = response.content["application/problem+json"].schema;
  return schema.$ref ? compileReference(schema.$ref) : ajv.compile(schema);
}

function expectValid(validate, value, name) {
  if (!validate(value)) {
    throw new Error(
      `${name} should be valid: ${formatErrors(validate.errors)}`,
    );
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
const legacyModelEvidence = { status: "legacy-unmeasured" };
const measuredModelEvidence = {
  status: "measured",
  datasetVersion: "reactorfront-synthetic-documents-v1",
  datasetSha256:
    "e82005c8ca78b7966f24e1faaf2a2b161262f1e774dc813e0c2d0743280cb046",
  preprocessingVersion: "nfkc-ascii-alphanumeric-bow-v1",
  pipelineVersion: "pytorch-multinomial-naive-bayes-linear-v1",
  artifactSha256:
    "82996b9d7a715ee8aee3b9b291cb9538346d84f5398c6b4448c1c79725e9c2ac",
  evaluationPolicyVersion: "document-classification-evaluation-v1",
  evaluationPolicySha256:
    "e3431c6d4e9094b8bd88b77a4ba4abc860641d7f83eaf71a5ee71c8f46bae332",
  evaluationReportSha256:
    "1337d7bf0368799ebd2bc088cfda16544ca78c3ed77f96ba265a7d9b090a19b5",
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
    modelEvidence: measuredModelEvidence,
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

const reviewDecisionRequest = compileReference(
  "#/components/schemas/ReviewDecisionRequest",
);
expectValid(
  reviewDecisionRequest,
  { finalClassification: "invoice" },
  "review decision request",
);
expectInvalid(
  reviewDecisionRequest,
  {
    finalClassification: "invoice",
    reviewerPrincipalId: "55555555-5555-4555-8555-555555555555",
  },
  "review decision request with actor override",
);

const review = compileReference("#/components/schemas/Review");
const terminalReview = compileReference("#/components/schemas/TerminalReview");
const reviewIdentity = {
  documentId: "22222222-2222-4222-8222-222222222222",
  jobId: "33333333-3333-4333-8333-333333333333",
  machineClassification: "invoice",
  machineConfidence: 0.98,
  modelVersion: "document-type-v1",
  modelEvidence: legacyModelEvidence,
};
const terminalIdentity = {
  ...reviewIdentity,
  reviewVersion: 1,
  reviewerPrincipalId: "55555555-5555-4555-8555-555555555555",
  decidedAt: "2026-08-01T00:00:00Z",
};
const validReviews = [
  { ...reviewIdentity, status: "unreviewed", reviewVersion: 0 },
  {
    ...terminalIdentity,
    status: "approved",
    finalClassification: "invoice",
  },
  {
    ...terminalIdentity,
    status: "corrected",
    finalClassification: "report",
  },
];

for (const reviewState of validReviews) {
  expectValid(review, reviewState, `review state ${reviewState.status}`);
  if (reviewState.status !== "unreviewed") {
    expectValid(
      terminalReview,
      reviewState,
      `terminal review state ${reviewState.status}`,
    );
  }
}

const invalidReviewStates = [
  {
    name: "approved review with changed classification",
    value: {
      ...terminalIdentity,
      status: "approved",
      finalClassification: "report",
    },
  },
  {
    name: "corrected review with unchanged classification",
    value: {
      ...terminalIdentity,
      status: "corrected",
      finalClassification: "invoice",
    },
  },
];

for (const invalidCase of invalidReviewStates) {
  expectInvalid(review, invalidCase.value, invalidCase.name);
  expectInvalid(terminalReview, invalidCase.value, invalidCase.name);
}

const correlationId = "11111111-1111-4111-8111-111111111111";
const auditEvent = compileReference("#/components/schemas/AuditEvent");
const auditIdentity = {
  eventId: "44444444-4444-4444-8444-444444444444",
  occurredAt: "2026-08-01T00:00:00Z",
  actorPrincipalId: "55555555-5555-4555-8555-555555555555",
  documentId: documentIdentity.documentId,
  jobId: documentIdentity.jobId,
  correlationId,
};
const measuredAuditDetails = {
  modelEvidenceStatus: "measured",
  modelVersion: "document-type-v1",
  datasetVersion: measuredModelEvidence.datasetVersion,
  datasetSha256: measuredModelEvidence.datasetSha256,
  preprocessingVersion: measuredModelEvidence.preprocessingVersion,
  pipelineVersion: measuredModelEvidence.pipelineVersion,
  artifactSha256: measuredModelEvidence.artifactSha256,
  evaluationPolicyVersion: measuredModelEvidence.evaluationPolicyVersion,
  evaluationPolicySha256: measuredModelEvidence.evaluationPolicySha256,
  evaluationReportSha256: measuredModelEvidence.evaluationReportSha256,
};
const legacyAudit = {
  ...auditIdentity,
  action: "document.submitted",
  detailsVersion: 1,
  details: {},
};
const measuredAudit = {
  ...auditIdentity,
  action: "processing.completed",
  detailsVersion: 2,
  details: measuredAuditDetails,
};
expectValid(auditEvent, legacyAudit, "legacy audit event");
expectValid(auditEvent, measuredAudit, "measured lineage audit event");
expectInvalid(
  auditEvent,
  { ...legacyAudit, details: measuredAuditDetails },
  "version 1 audit with measured details",
);
expectInvalid(
  auditEvent,
  { ...measuredAudit, details: {} },
  "version 2 audit without measured details",
);
expectInvalid(
  auditEvent,
  { ...measuredAudit, action: "review.approved" },
  "version 2 non-completion audit",
);

const authenticationContracts = [
  {
    responseName: "AuthenticationRequired",
    httpStatus: 401,
    code: "AUTHENTICATION_REQUIRED",
  },
  {
    responseName: "InsufficientCapability",
    httpStatus: 403,
    code: "INSUFFICIENT_CAPABILITY",
  },
];
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
    httpStatus: 422,
    code: "INVALID_REQUEST",
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
    httpStatus: 422,
    code: "INVALID_REQUEST",
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

for (const contract of authenticationContracts) {
  const validate = componentResponseValidator(contract.responseName);
  const validProblem = {
    type: `urn:reactorfront:problem:${contract.code.toLowerCase().replaceAll("_", "-")}`,
    title: "Stable public problem",
    status: contract.httpStatus,
    code: contract.code,
    correlationId,
  };
  expectValid(validate, validProblem, contract.responseName);
  expectInvalid(
    validate,
    { ...validProblem, status: contract.httpStatus === 401 ? 403 : 401 },
    `${contract.responseName} with mismatched body status`,
  );
}

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

  expectValid(
    validate,
    validProblem,
    `${contract.httpStatus} ${contract.code}`,
  );
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
    `${validReviews.length} review states with ` +
    `${invalidReviewStates.length} invalid review states, and ` +
    `2 valid audit events with 3 invalid audit events, and ` +
    `${problemContracts.length * 2 + authenticationContracts.length} ` +
    `invalid problem cases.`,
);
