import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page, type Response } from "@playwright/test";

import { canonicalInvoicePdf } from "./pdf-fixture";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu;
const ARTIFACT_ROOT = path.resolve("artifacts/verification");

interface AcceptedPayload {
  documentId: string;
  jobId: string;
  status: "accepted";
}

interface CompletedPayload {
  documentId: string;
  jobId: string;
  status: "completed";
  classification: "invoice" | "report";
  confidence: number;
  modelVersion: string;
}

interface FailedPayload {
  documentId: string;
  jobId: string;
  status: "failed";
  failureCode: string;
}

function sourcePdfInput(page: Page) {
  return page.getByLabel("Source PDF", { exact: true });
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
): Promise<{ upload: Response; terminal: Response }> {
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
  await page.getByRole("button", { name: "Start classification" }).click();
  return { upload: await uploadResponse, terminal: await terminalResponse };
}

async function responseJson<T>(response: Response): Promise<T> {
  return (await response.json()) as T;
}

test("proves completed, failed, correlation, and invalid-file browser paths", async ({
  page,
}) => {
  test.slow();
  mkdirSync(ARTIFACT_ROOT, { recursive: true });
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
    }),
  ).toBeVisible();

  const completedResponses = await upload(
    page,
    {
      name: "canonical-invoice.pdf",
      mimeType: "application/pdf",
      buffer: canonicalInvoicePdf(),
    },
    "completed",
  );
  const accepted = await responseJson<AcceptedPayload>(
    completedResponses.upload,
  );
  const completed = await responseJson<CompletedPayload>(
    completedResponses.terminal,
  );
  const completedUploadCorrelation = await correlationPair(
    completedResponses.upload,
  );
  const completedPollCorrelation = await correlationPair(
    completedResponses.terminal,
  );

  expect(completedResponses.upload.status()).toBe(202);
  expect(accepted.status).toBe("accepted");
  expect(accepted.documentId).toMatch(UUID_PATTERN);
  expect(accepted.jobId).toMatch(UUID_PATTERN);
  expect(completed).toMatchObject({
    documentId: accepted.documentId,
    jobId: accepted.jobId,
    status: "completed",
    classification: "invoice",
  });
  expect(completed.confidence).toBeGreaterThanOrEqual(0.7);
  expect(completed.modelVersion).toBe("document-type-v1");
  await expect(page.getByText("invoice", { exact: true })).toBeVisible();
  await expect(
    page.getByText(`${(completed.confidence * 100).toFixed(1)}%`, {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(completed.modelVersion, { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: path.join(ARTIFACT_ROOT, "e2e-completed.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "Classify another PDF" }).click();
  const failedResponses = await upload(
    page,
    {
      name: "invalid-structure.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.7\ninvalid", "ascii"),
    },
    "failed",
  );
  const failedAccepted = await responseJson<AcceptedPayload>(
    failedResponses.upload,
  );
  const failed = await responseJson<FailedPayload>(failedResponses.terminal);
  const failedUploadCorrelation = await correlationPair(failedResponses.upload);
  const failedPollCorrelation = await correlationPair(failedResponses.terminal);

  expect(failedAccepted.status).toBe("accepted");
  expect(failed).toMatchObject({
    documentId: failedAccepted.documentId,
    jobId: failedAccepted.jobId,
    status: "failed",
    failureCode: "INVALID_PDF",
  });
  await expect(page.getByText("Failed", { exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("INVALID_PDF");
  await page.screenshot({
    path: path.join(ARTIFACT_ROOT, "e2e-failed-terminal.png"),
    fullPage: true,
  });

  await page.getByRole("button", { name: "Classify another PDF" }).click();
  const requestsBeforeInvalidFile = uploadRequests;
  await sourcePdfInput(page).setInputFiles({
    name: "not-a-pdf.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("not a pdf", "utf8"),
  });
  await page.getByRole("button", { name: "Start classification" }).click();
  await expect(page.getByRole("alert")).toContainText("application/pdf");
  expect(uploadRequests).toBe(requestsBeforeInvalidFile);

  writeFileSync(
    path.join(ARTIFACT_ROOT, "e2e-result.json"),
    `${JSON.stringify(
      {
        completed: {
          ...completed,
          uploadCorrelation: completedUploadCorrelation,
          pollCorrelation: completedPollCorrelation,
        },
        failed: {
          ...failed,
          uploadCorrelation: failedUploadCorrelation,
          pollCorrelation: failedPollCorrelation,
        },
        invalidFile: { apiRequestCreated: false },
      },
      null,
      2,
    )}\n`,
    "utf8",
  );
});
