import { createHash, randomUUID } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page, type Response } from "@playwright/test";

import {
  canonicalInvoicePdf,
  syntheticCorrectionReportPdf,
} from "./pdf-fixture";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu;
const ENTITY_TAG_PATTERN = /^"[a-f0-9]{64}"$/u;
const ARTIFACT_ROOT = path.resolve("artifacts/verification");
const PRIVATE_ARTIFACT_ROOT = path.resolve("artifacts/private-verification");
const SENSITIVE_CANARY_MANIFEST = path.join(
  ARTIFACT_ROOT,
  ".artifact-sensitive-canaries.json",
);

interface SensitiveCanary {
  category:
    | "private profile claim"
    | "submitted private data"
    | "submitted source text";
  encoding: "base64" | "utf8";
  value: string;
}

function sensitiveCanary(
  category: SensitiveCanary["category"],
  value: Buffer | string,
): SensitiveCanary {
  return typeof value === "string"
    ? { category, encoding: "utf8", value }
    : { category, encoding: "base64", value: value.toString("base64") };
}

function sourceTextCanaries(file: string): SensitiveCanary[] {
  return readFileSync(file, "utf8")
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => sensitiveCanary("submitted source text", line));
}

function writeSensitiveCanaryManifest(canaries: SensitiveCanary[]): void {
  writeFileSync(
    SENSITIVE_CANARY_MANIFEST,
    `${JSON.stringify({ version: 1, canaries }, null, 2)}\n`,
    "utf8",
  );
}

function registerObservedPrivateProfileCanaries(
  canaries: SensitiveCanary[],
  ...values: unknown[]
): void {
  let changed = false;
  for (const value of values) {
    if (typeof value !== "string" || Buffer.byteLength(value, "utf8") < 8) {
      continue;
    }
    const duplicate = canaries.some(
      (canary) =>
        canary.category === "private profile claim" &&
        canary.encoding === "utf8" &&
        canary.value === value,
    );
    if (!duplicate) {
      canaries.push(sensitiveCanary("private profile claim", value));
      changed = true;
    }
  }
  if (changed) {
    writeSensitiveCanaryManifest(canaries);
  }
}

interface AcceptedPayload {
  documentId: string;
  jobId: string;
  status: "accepted";
}

interface ModelEvidence {
  status: "measured";
  datasetVersion: string;
  datasetSha256: string;
  preprocessingVersion: string;
  pipelineVersion: string;
  artifactSha256: string;
  evaluationPolicyVersion: string;
  evaluationPolicySha256: string;
  evaluationReportSha256: string;
}

const EXPECTED_MODEL_EVIDENCE: ModelEvidence = {
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

const EXPECTED_AUDIT_LINEAGE = {
  modelEvidenceStatus: "measured",
  modelVersion: "document-type-v1",
  datasetVersion: EXPECTED_MODEL_EVIDENCE.datasetVersion,
  datasetSha256: EXPECTED_MODEL_EVIDENCE.datasetSha256,
  preprocessingVersion: EXPECTED_MODEL_EVIDENCE.preprocessingVersion,
  pipelineVersion: EXPECTED_MODEL_EVIDENCE.pipelineVersion,
  artifactSha256: EXPECTED_MODEL_EVIDENCE.artifactSha256,
  evaluationPolicyVersion: EXPECTED_MODEL_EVIDENCE.evaluationPolicyVersion,
  evaluationPolicySha256: EXPECTED_MODEL_EVIDENCE.evaluationPolicySha256,
  evaluationReportSha256: EXPECTED_MODEL_EVIDENCE.evaluationReportSha256,
};

interface CompletedPayload {
  documentId: string;
  jobId: string;
  status: "completed";
  classification: "invoice" | "report";
  confidence: number;
  modelVersion: string;
  modelEvidence: ModelEvidence;
}

interface FailedPayload {
  documentId: string;
  jobId: string;
  status: "failed";
  failureCode: string;
}

interface ReviewPayload {
  documentId: string;
  jobId: string;
  status: "unreviewed" | "approved" | "corrected";
  machineClassification: "invoice" | "report";
  machineConfidence: number;
  modelVersion: string;
  modelEvidence: ModelEvidence;
  reviewVersion: 0 | 1;
  finalClassification?: "invoice" | "report";
  reviewerPrincipalId?: string;
  decidedAt?: string;
}

interface BrowserFetchResult {
  status: number;
  contentType: string;
  entityTag: string | null;
  body: Record<string, unknown> | null;
}

interface AuditEventEvidence {
  action: string;
  actorPrincipalId: string;
  correlationId: string;
  reviewId?: string;
  detailsVersion: number;
  details: Record<string, unknown>;
}

function sourcePdfInput(page: Page) {
  return page.getByLabel("Source PDF", { exact: true });
}

function workflowAlert(page: Page, expectedText: string) {
  return page.getByRole("alert").filter({ hasText: expectedText });
}

function documentResponse(
  response: Response,
  status: string,
): Promise<boolean> | boolean {
  const url = new URL(response.url());
  if (
    response.request().method() !== "GET" ||
    !url.pathname.startsWith("/api/documents/") ||
    !response.ok()
  ) {
    return false;
  }
  return response
    .json()
    .then((payload: unknown) => {
      return (
        typeof payload === "object" &&
        payload !== null &&
        "status" in payload &&
        payload.status === status
      );
    })
    .catch(() => false);
}

function reviewResponse(
  response: Response,
  method: "GET" | "PUT",
  status: ReviewPayload["status"],
): Promise<boolean> | boolean {
  const url = new URL(response.url());
  if (
    response.request().method() !== method ||
    !url.pathname.endsWith("/review") ||
    !response.ok()
  ) {
    return false;
  }
  return response
    .json()
    .then((payload: unknown) => {
      return (
        typeof payload === "object" &&
        payload !== null &&
        "status" in payload &&
        payload.status === status
      );
    })
    .catch(() => false);
}

async function correlationPair(response: Response): Promise<{
  request: string;
  response: string;
}> {
  const requestCorrelation = await response
    .request()
    .headerValue("X-Correlation-ID");
  const responseCorrelation = await response.headerValue("X-Correlation-ID");
  expect(requestCorrelation).toMatch(UUID_PATTERN);
  expect(responseCorrelation).toBe(requestCorrelation);
  return { request: requestCorrelation!, response: responseCorrelation! };
}

async function upload(
  page: Page,
  file: { name: string; mimeType: string; buffer: Buffer },
  terminalStatus: "completed" | "failed",
): Promise<{
  upload: Response;
  terminal: Response;
  review?: Response;
}> {
  await sourcePdfInput(page).setInputFiles(file);
  const uploadResponse = page.waitForResponse((response) => {
    return (
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/documents"
    );
  });
  const terminalResponse = page.waitForResponse((response) =>
    documentResponse(response, terminalStatus),
  );
  const review =
    terminalStatus === "completed"
      ? page.waitForResponse((response) =>
          reviewResponse(response, "GET", "unreviewed"),
        )
      : undefined;
  await page
    .getByRole("button", { name: "Start classification", exact: true })
    .click();
  const result = {
    upload: await uploadResponse,
    terminal: await terminalResponse,
  };
  return review === undefined ? result : { ...result, review: await review };
}

async function responseJson<T>(response: Response): Promise<T> {
  return (await response.json()) as T;
}

async function browserJsonRequest(
  page: Page,
  pathName: string,
  init: {
    method?: string;
    headers?: Record<string, string>;
    body?: string;
  } = {},
): Promise<BrowserFetchResult> {
  return page.evaluate(
    async ({ pathName: target, init: requestInit }) => {
      const response = await fetch(target, {
        ...requestInit,
        credentials: "same-origin",
      });
      const contentType = response.headers.get("Content-Type") ?? "";
      let body: Record<string, unknown> | null = null;
      if (contentType.includes("json")) {
        body = (await response.json()) as Record<string, unknown>;
      }
      return {
        status: response.status,
        contentType,
        entityTag: response.headers.get("ETag"),
        body,
      };
    },
    { pathName, init },
  );
}

function auditEvents(
  result: BrowserFetchResult,
  sensitiveCanaries: SensitiveCanary[],
): AuditEventEvidence[] {
  const events = result.body?.events;
  if (!Array.isArray(events)) {
    throw new Error("Audit history did not contain an event array.");
  }
  registerObservedPrivateProfileCanaries(
    sensitiveCanaries,
    ...events.map((event) =>
      typeof event === "object" && event !== null
        ? (event as Record<string, unknown>).actorPrincipalId
        : undefined,
    ),
  );
  return events.map((event) => {
    if (typeof event !== "object" || event === null) {
      throw new Error("Audit history contained an invalid event.");
    }
    const candidate = event as Record<string, unknown>;
    if (
      typeof candidate.action !== "string" ||
      typeof candidate.actorPrincipalId !== "string" ||
      typeof candidate.correlationId !== "string" ||
      typeof candidate.detailsVersion !== "number" ||
      typeof candidate.details !== "object" ||
      candidate.details === null ||
      (candidate.reviewId !== undefined &&
        typeof candidate.reviewId !== "string")
    ) {
      throw new Error("Audit history contained incomplete event evidence.");
    }
    return {
      action: candidate.action,
      actorPrincipalId: candidate.actorPrincipalId,
      correlationId: candidate.correlationId,
      detailsVersion: candidate.detailsVersion,
      details: candidate.details as Record<string, unknown>,
      ...(candidate.reviewId === undefined
        ? {}
        : { reviewId: candidate.reviewId }),
    };
  });
}

async function privateSourceProof(
  page: Page,
  documentId: string,
): Promise<{
  status: number;
  contentType: string;
  entityTag: string | null;
  length: number;
  sha256: string;
  pdfMagic: boolean;
}> {
  return page.evaluate(async (id) => {
    const response = await fetch(
      `/api/documents/${encodeURIComponent(id)}/source`,
      {
        headers: { "X-Correlation-ID": crypto.randomUUID() },
        credentials: "same-origin",
      },
    );
    const content = await response.arrayBuffer();
    const digest = Array.from(
      new Uint8Array(await crypto.subtle.digest("SHA-256", content)),
      (value) => value.toString(16).padStart(2, "0"),
    ).join("");
    const prefix = new TextDecoder("ascii").decode(content.slice(0, 5));
    return {
      status: response.status,
      contentType: response.headers.get("Content-Type") ?? "",
      entityTag: response.headers.get("ETag"),
      length: content.byteLength,
      sha256: digest,
      pdfMagic: prefix === "%PDF-",
    };
  }, documentId);
}

async function assertSource(
  page: Page,
  accepted: AcceptedPayload,
  source: Buffer,
) {
  const proof = await privateSourceProof(page, accepted.documentId);
  expect(proof).toMatchObject({
    status: 200,
    contentType: "application/pdf",
    length: source.byteLength,
    sha256: createHash("sha256").update(source).digest("hex"),
    pdfMagic: true,
  });
  expect(proof.entityTag).toBe(`"${proof.sha256}"`);
  return proof;
}

test("proves authenticated approval, correction, audit, negative, and recovery paths", async ({
  page,
}) => {
  test.slow();
  mkdirSync(ARTIFACT_ROOT, { recursive: true });
  mkdirSync(PRIVATE_ARTIFACT_ROOT, { recursive: true });
  const invoiceSource = canonicalInvoicePdf();
  const correctionSource = syntheticCorrectionReportPdf();
  const invalidPdfSource = Buffer.from("%PDF-1.7\ninvalid", "ascii");
  const invalidLocalSource = Buffer.from("not a pdf", "utf8");
  const sensitiveCanaries = [
    sensitiveCanary("private profile claim", "reviewer@synthetic.invalid"),
    sensitiveCanary("private profile claim", "synthetic-reviewer"),
    sensitiveCanary("private profile claim", "reactorfront-reviewers"),
    sensitiveCanary("submitted private data", invoiceSource),
    sensitiveCanary("submitted private data", correctionSource),
    sensitiveCanary("submitted private data", invalidPdfSource),
    sensitiveCanary("submitted private data", invalidLocalSource),
    ...sourceTextCanaries("tests/fixtures/canonical_invoice.txt"),
    ...sourceTextCanaries("tests/fixtures/synthetic_correction_report.txt"),
  ];
  writeSensitiveCanaryManifest(sensitiveCanaries);
  let uploadRequests = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/documents"
    ) {
      uploadRequests += 1;
    }
  });

  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "From source PDF to a traceable ML result.",
      exact: true,
    }),
  ).toBeVisible();
  const anonymous = await browserJsonRequest(
    page,
    `/api/documents/${randomUUID()}/review`,
  );
  expect(anonymous.status).toBe(401);

  await page
    .getByRole("link", {
      name: "Sign in as synthetic reviewer",
      exact: true,
    })
    .click();
  await page.locator('input[name="login"]').fill("reviewer@synthetic.invalid");
  await page.locator('input[name="password"]').fill("password");
  await page.locator('button[type="submit"]').click();
  await expect(
    page.getByText("Synthetic reviewer signed in", { exact: true }),
  ).toBeVisible();
  await expect(sourcePdfInput(page)).toBeVisible();
  expect(
    await page.evaluate(() => ({
      local: Object.keys(localStorage),
      session: Object.keys(sessionStorage),
    })),
  ).toEqual({ local: [], session: [] });

  const approvalResponses = await upload(
    page,
    {
      name: "canonical-invoice.pdf",
      mimeType: "application/pdf",
      buffer: invoiceSource,
    },
    "completed",
  );
  const approvalAccepted = await responseJson<AcceptedPayload>(
    approvalResponses.upload,
  );
  const approvalCompleted = await responseJson<CompletedPayload>(
    approvalResponses.terminal,
  );
  const approvalInitialReview = await responseJson<ReviewPayload>(
    approvalResponses.review!,
  );
  const approvalInitialTag =
    await approvalResponses.review!.headerValue("ETag");
  expect(approvalCompleted).toMatchObject({
    documentId: approvalAccepted.documentId,
    jobId: approvalAccepted.jobId,
    status: "completed",
    classification: "invoice",
    modelVersion: "document-type-v1",
  });
  expect(approvalCompleted.confidence).toBeGreaterThanOrEqual(0.7);
  expect(approvalCompleted.modelEvidence).toEqual(EXPECTED_MODEL_EVIDENCE);
  expect(approvalInitialReview).toMatchObject({
    documentId: approvalAccepted.documentId,
    status: "unreviewed",
    machineClassification: "invoice",
    reviewVersion: 0,
    modelEvidence: EXPECTED_MODEL_EVIDENCE,
  });
  expect(approvalInitialTag).toMatch(ENTITY_TAG_PATTERN);
  await expect(
    page.getByText("Machine classification", { exact: true }),
  ).toBeVisible();
  const approvalSource = await assertSource(
    page,
    approvalAccepted,
    invoiceSource,
  );

  const noCsrf = await browserJsonRequest(
    page,
    `/api/documents/${approvalAccepted.documentId}/review`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "If-Match": approvalInitialTag!,
        "Idempotency-Key": randomUUID(),
        "X-Correlation-ID": randomUUID(),
      },
      body: JSON.stringify({ finalClassification: "invoice" }),
    },
  );
  expect(noCsrf.status).toBe(403);
  expect(noCsrf.body?.code).toMatch(/^WEB_CSRF_/u);
  const unchangedAfterCsrf = await browserJsonRequest(
    page,
    `/api/documents/${approvalAccepted.documentId}/review`,
  );
  expect(unchangedAfterCsrf.body?.status).toBe("unreviewed");

  const approvalDecisionResponse = page.waitForResponse((response) =>
    reviewResponse(response, "PUT", "approved"),
  );
  await page
    .getByRole("button", {
      name: "Approve invoice classification",
      exact: true,
    })
    .click();
  const approvalDecision = await approvalDecisionResponse;
  const approved = await responseJson<ReviewPayload>(approvalDecision);
  registerObservedPrivateProfileCanaries(
    sensitiveCanaries,
    approved.reviewerPrincipalId,
  );
  const approvalDecisionCorrelation = await correlationPair(approvalDecision);
  const approvalRequestHeaders = {
    csrf: await approvalDecision.request().headerValue("X-CSRF-Token"),
    entityTag: await approvalDecision.request().headerValue("If-Match"),
    idempotencyKey: await approvalDecision
      .request()
      .headerValue("Idempotency-Key"),
  };
  expect(approvalRequestHeaders.csrf).toBeTruthy();
  expect(approvalRequestHeaders.entityTag).toBe(approvalInitialTag);
  expect(approvalRequestHeaders.idempotencyKey).toMatch(UUID_PATTERN);
  expect(approved).toMatchObject({
    status: "approved",
    machineClassification: "invoice",
    finalClassification: "invoice",
    reviewVersion: 1,
  });
  expect(approved.reviewerPrincipalId).toMatch(UUID_PATTERN);
  await expect(
    page.getByText("review.approved", { exact: true }),
  ).toBeVisible();
  const approvalAudit = await browserJsonRequest(
    page,
    `/api/documents/${approvalAccepted.documentId}/audit-events`,
  );
  const approvalAuditEvents = auditEvents(approvalAudit, sensitiveCanaries);
  const approvalAuditActions = approvalAuditEvents.map((event) => event.action);
  expect(approvalAuditActions).toEqual([
    "document.submitted",
    "processing.completed",
    "review.approved",
  ]);
  expect(approvalAuditEvents[1]).toMatchObject({
    detailsVersion: 2,
    details: EXPECTED_AUDIT_LINEAGE,
  });
  expect(approvalAuditEvents.at(-1)).toMatchObject({
    actorPrincipalId: approved.reviewerPrincipalId,
    correlationId: approvalDecisionCorrelation.response,
  });
  expect(approvalAuditEvents.at(-1)?.reviewId).toMatch(UUID_PATTERN);

  const identicalReplay = await browserJsonRequest(
    page,
    `/api/documents/${approvalAccepted.documentId}/review`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": approvalRequestHeaders.csrf!,
        "If-Match": approvalRequestHeaders.entityTag!,
        "Idempotency-Key": approvalRequestHeaders.idempotencyKey!,
        "X-Correlation-ID": randomUUID(),
      },
      body: JSON.stringify({ finalClassification: "invoice" }),
    },
  );
  expect(identicalReplay.status).toBe(200);
  expect(identicalReplay.body?.status).toBe("approved");

  const staleDecision = await browserJsonRequest(
    page,
    `/api/documents/${approvalAccepted.documentId}/review`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": approvalRequestHeaders.csrf!,
        "If-Match": approvalRequestHeaders.entityTag!,
        "Idempotency-Key": randomUUID(),
        "X-Correlation-ID": randomUUID(),
      },
      body: JSON.stringify({ finalClassification: "report" }),
    },
  );
  expect(staleDecision.status).toBe(412);
  expect(staleDecision.body?.code).toBe("PRECONDITION_FAILED");
  await page.screenshot({
    path: path.join(PRIVATE_ARTIFACT_ROOT, "e2e-approved-review.png"),
    fullPage: true,
  });

  await page
    .getByRole("button", { name: "Classify another PDF", exact: true })
    .click();
  const correctionResponses = await upload(
    page,
    {
      name: "synthetic-correction-report.pdf",
      mimeType: "application/pdf",
      buffer: correctionSource,
    },
    "completed",
  );
  const correctionAccepted = await responseJson<AcceptedPayload>(
    correctionResponses.upload,
  );
  const correctionCompleted = await responseJson<CompletedPayload>(
    correctionResponses.terminal,
  );
  expect(correctionCompleted).toMatchObject({
    documentId: correctionAccepted.documentId,
    status: "completed",
    classification: "invoice",
    modelVersion: "document-type-v1",
    modelEvidence: EXPECTED_MODEL_EVIDENCE,
  });
  const correctionSourceProof = await assertSource(
    page,
    correctionAccepted,
    correctionSource,
  );
  await page.getByRole("radio", { name: "report", exact: true }).click();
  const correctionDecisionResponse = page.waitForResponse((response) =>
    reviewResponse(response, "PUT", "corrected"),
  );
  await page
    .getByRole("button", {
      name: "Correct classification to report",
      exact: true,
    })
    .click();
  const correctionDecision = await correctionDecisionResponse;
  const corrected = await responseJson<ReviewPayload>(correctionDecision);
  registerObservedPrivateProfileCanaries(
    sensitiveCanaries,
    corrected.reviewerPrincipalId,
  );
  const correctionDecisionCorrelation =
    await correlationPair(correctionDecision);
  expect(corrected).toMatchObject({
    status: "corrected",
    machineClassification: "invoice",
    finalClassification: "report",
    reviewVersion: 1,
  });
  expect(corrected.reviewerPrincipalId).toBe(approved.reviewerPrincipalId);
  await expect(
    page.getByText("review.corrected", { exact: true }),
  ).toBeVisible();
  const correctionAudit = await browserJsonRequest(
    page,
    `/api/documents/${correctionAccepted.documentId}/audit-events`,
  );
  const correctionAuditEvents = auditEvents(correctionAudit, sensitiveCanaries);
  const correctionAuditActions = correctionAuditEvents.map(
    (event) => event.action,
  );
  expect(correctionAuditActions).toEqual([
    "document.submitted",
    "processing.completed",
    "review.corrected",
  ]);
  expect(correctionAuditEvents[1]).toMatchObject({
    detailsVersion: 2,
    details: EXPECTED_AUDIT_LINEAGE,
  });
  expect(correctionAuditEvents.at(-1)).toMatchObject({
    actorPrincipalId: corrected.reviewerPrincipalId,
    correlationId: correctionDecisionCorrelation.response,
  });
  expect(correctionAuditEvents.at(-1)?.reviewId).toMatch(UUID_PATTERN);
  await page.screenshot({
    path: path.join(PRIVATE_ARTIFACT_ROOT, "e2e-corrected-review.png"),
    fullPage: true,
  });

  await page
    .getByRole("button", { name: "Classify another PDF", exact: true })
    .click();
  const failedResponses = await upload(
    page,
    {
      name: "invalid-structure.pdf",
      mimeType: "application/pdf",
      buffer: invalidPdfSource,
    },
    "failed",
  );
  const failedAccepted = await responseJson<AcceptedPayload>(
    failedResponses.upload,
  );
  const failed = await responseJson<FailedPayload>(failedResponses.terminal);
  expect(failed).toMatchObject({
    documentId: failedAccepted.documentId,
    jobId: failedAccepted.jobId,
    status: "failed",
    failureCode: "INVALID_PDF",
  });
  await expect(workflowAlert(page, "INVALID_PDF")).toBeVisible();

  await page
    .getByRole("button", { name: "Classify another PDF", exact: true })
    .click();
  const requestsBeforeInvalidFile = uploadRequests;
  await sourcePdfInput(page).setInputFiles({
    name: "not-a-pdf.txt",
    mimeType: "text/plain",
    buffer: invalidLocalSource,
  });
  await page
    .getByRole("button", { name: "Start classification", exact: true })
    .click();
  await expect(workflowAlert(page, "application/pdf")).toBeVisible();
  expect(uploadRequests).toBe(requestsBeforeInvalidFile);

  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("link", {
      name: "Sign in as synthetic reviewer",
      exact: true,
    }),
  ).toBeVisible();
  const deniedAfterSignOut = await Promise.all(
    [
      `/api/documents/${approvalAccepted.documentId}/source`,
      `/api/documents/${approvalAccepted.documentId}/review`,
      `/api/documents/${approvalAccepted.documentId}/audit-events`,
    ].map((target) => browserJsonRequest(page, target)),
  );
  expect(deniedAfterSignOut.map((result) => result.status)).toEqual([
    401, 401, 401,
  ]);
  expect(
    await page.evaluate(() => ({
      local: Object.keys(localStorage),
      session: Object.keys(sessionStorage),
    })),
  ).toEqual({ local: [], session: [] });

  const completedUploadCorrelation = await correlationPair(
    approvalResponses.upload,
  );
  const completedPollCorrelation = await correlationPair(
    approvalResponses.terminal,
  );
  const correctionUploadCorrelation = await correlationPair(
    correctionResponses.upload,
  );
  const correctionPollCorrelation = await correlationPair(
    correctionResponses.terminal,
  );
  const failedUploadCorrelation = await correlationPair(failedResponses.upload);
  const failedPollCorrelation = await correlationPair(failedResponses.terminal);

  writeFileSync(
    path.join(ARTIFACT_ROOT, "e2e-result.json"),
    `${JSON.stringify(
      {
        completed: {
          ...approvalCompleted,
          source: approvalSource,
          decision: {
            status: approved.status,
            finalClassification: approved.finalClassification,
            reviewVersion: approved.reviewVersion,
            reviewerPrincipalId: approved.reviewerPrincipalId,
            decidedAt: approved.decidedAt,
            correlation: approvalDecisionCorrelation,
          },
          auditActions: approvalAuditActions,
          identicalReplayStatus: identicalReplay.status,
          staleDecision: {
            status: staleDecision.status,
            code: staleDecision.body?.code,
          },
          csrfRejection: { status: noCsrf.status, code: noCsrf.body?.code },
          uploadCorrelation: completedUploadCorrelation,
          pollCorrelation: completedPollCorrelation,
        },
        correction: {
          ...correctionCompleted,
          humanGroundTruth: "report",
          fixturePurpose: "synthetic correction proof, not model quality",
          source: correctionSourceProof,
          decision: {
            status: corrected.status,
            finalClassification: corrected.finalClassification,
            reviewVersion: corrected.reviewVersion,
            reviewerPrincipalId: corrected.reviewerPrincipalId,
            decidedAt: corrected.decidedAt,
            correlation: correctionDecisionCorrelation,
          },
          auditActions: correctionAuditActions,
          uploadCorrelation: correctionUploadCorrelation,
          pollCorrelation: correctionPollCorrelation,
        },
        failed: {
          ...failed,
          uploadCorrelation: failedUploadCorrelation,
          pollCorrelation: failedPollCorrelation,
        },
        invalidFile: { apiRequestCreated: false },
        security: {
          anonymousReviewStatus: anonymous.status,
          postSignOutStatuses: deniedAfterSignOut.map(
            (result) => result.status,
          ),
          browserTokenStorage: false,
        },
      },
      null,
      2,
    )}\n`,
    "utf8",
  );
});
