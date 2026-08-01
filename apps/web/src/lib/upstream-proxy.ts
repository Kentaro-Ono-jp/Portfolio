import type { z } from "zod";

import {
  auditHistorySchema,
  correlationIdSchema,
  documentAcceptedSchema,
  documentIdSchema,
  documentStatusSchema,
  problemSchema,
  reviewDecisionRequestSchema,
  reviewEntityTagSchema,
  reviewSchema,
  terminalReviewSchema,
  type Problem,
} from "@/lib/contracts";
import { readServerConfig } from "@/lib/server-config";

const JSON_MEDIA_TYPE = "application/json";
const PROBLEM_MEDIA_TYPE = "application/problem+json";
const PDF_MEDIA_TYPE = "application/pdf";
const MAX_DOCUMENT_BYTES = 5 * 1024 * 1024;

interface ProxyDependencies {
  fetch: typeof fetch;
  environment: Readonly<Record<string, string | undefined>>;
  createCorrelationId: () => string;
  timeoutSignal: (milliseconds: number) => AbortSignal;
}

export type ProxyDependencyOverrides = Partial<ProxyDependencies>;

class InvalidUpstreamResponseError extends Error {
  constructor() {
    super("The upstream response did not satisfy the public contract.");
    this.name = "InvalidUpstreamResponseError";
  }
}

function dependencies(overrides: ProxyDependencyOverrides): ProxyDependencies {
  return {
    fetch: globalThis.fetch,
    environment: process.env,
    createCorrelationId: () => crypto.randomUUID(),
    timeoutSignal: (milliseconds) => AbortSignal.timeout(milliseconds),
    ...overrides,
  };
}

function requestCorrelationId(
  request: Request,
  createCorrelationId: () => string,
): string {
  const candidate = request.headers.get("X-Correlation-ID");
  const parsed = correlationIdSchema.safeParse(candidate);
  return parsed.success ? parsed.data : createCorrelationId();
}

function problemResponse(problem: Problem, correlationId: string): Response {
  return Response.json(problem, {
    status: problem.status,
    headers: {
      "Content-Type": PROBLEM_MEDIA_TYPE,
      "X-Correlation-ID": correlationId,
      "Cache-Control": "private, no-store",
    },
  });
}

function webProblem(
  status: number,
  code: string,
  title: string,
  detail: string,
  correlationId: string,
): Response {
  return problemResponse(
    {
      type: `/problems/${code.toLowerCase().replaceAll("_", "-")}`,
      title,
      status,
      code,
      detail,
      correlationId,
    },
    correlationId,
  );
}

function mediaType(response: Response): string {
  return response.headers.get("Content-Type")?.split(";", 1)[0]?.trim() ?? "";
}

async function upstreamJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new InvalidUpstreamResponseError();
  }
}

async function validatedUpstreamResponse<T>(
  response: Response,
  expectedCorrelationId: string,
  successStatus: number,
  successSchema: z.ZodType<T>,
  successHeaders?: (response: Response) => HeadersInit,
): Promise<Response> {
  const upstreamCorrelation = correlationIdSchema.safeParse(
    response.headers.get("X-Correlation-ID"),
  );
  if (
    !upstreamCorrelation.success ||
    upstreamCorrelation.data !== expectedCorrelationId
  ) {
    throw new InvalidUpstreamResponseError();
  }

  if (response.status === successStatus) {
    if (mediaType(response) !== JSON_MEDIA_TYPE) {
      throw new InvalidUpstreamResponseError();
    }
    const parsed = successSchema.safeParse(await upstreamJson(response));
    if (!parsed.success) {
      throw new InvalidUpstreamResponseError();
    }
    const forwardedHeaders = successHeaders?.(response);
    return Response.json(parsed.data, {
      status: response.status,
      headers: {
        "X-Correlation-ID": upstreamCorrelation.data,
        ...forwardedHeaders,
      },
    });
  }

  if (response.status < 400 || mediaType(response) !== PROBLEM_MEDIA_TYPE) {
    throw new InvalidUpstreamResponseError();
  }
  const parsedProblem = problemSchema.safeParse(await upstreamJson(response));
  if (
    !parsedProblem.success ||
    parsedProblem.data.status !== response.status ||
    parsedProblem.data.correlationId !== upstreamCorrelation.data
  ) {
    throw new InvalidUpstreamResponseError();
  }
  return problemResponse(parsedProblem.data, upstreamCorrelation.data);
}

function isFile(value: FormDataEntryValue | null): value is File {
  return (
    value instanceof Blob && "name" in value && typeof value.name === "string"
  );
}

async function callUpstream<T>(
  request: Request,
  accessToken: string,
  path: string,
  init: RequestInit,
  successStatus: number,
  successSchema: z.ZodType<T>,
  overrides: ProxyDependencyOverrides,
  successHeaders?: (response: Response) => HeadersInit,
): Promise<Response> {
  const resolved = dependencies(overrides);
  const correlationId = requestCorrelationId(
    request,
    resolved.createCorrelationId,
  );

  try {
    const config = readServerConfig(resolved.environment);
    const headers = new Headers(init.headers);
    headers.set("Accept", `${JSON_MEDIA_TYPE}, ${PROBLEM_MEDIA_TYPE}`);
    headers.set("Authorization", `Bearer ${accessToken}`);
    headers.set("X-Correlation-ID", correlationId);
    const response = await resolved.fetch(
      new URL(path, `${config.apiBaseUrl}/`),
      {
        ...init,
        headers,
        signal: resolved.timeoutSignal(config.timeoutMilliseconds),
      },
    );
    return await validatedUpstreamResponse(
      response,
      correlationId,
      successStatus,
      successSchema,
      successHeaders,
    );
  } catch (error) {
    if (error instanceof InvalidUpstreamResponseError) {
      return webProblem(
        502,
        "WEB_INVALID_UPSTREAM_RESPONSE",
        "The processing service returned an invalid response.",
        "Please retry. If the problem continues, use the correlation ID when reporting it.",
        correlationId,
      );
    }
    return webProblem(
      503,
      "WEB_UPSTREAM_UNAVAILABLE",
      "The processing service is temporarily unavailable.",
      "Please wait a moment and try again.",
      correlationId,
    );
  }
}

function validatedReviewHeaders(response: Response): HeadersInit {
  const entityTag = reviewEntityTagSchema.safeParse(
    response.headers.get("ETag"),
  );
  if (!entityTag.success) {
    throw new InvalidUpstreamResponseError();
  }
  return { ETag: entityTag.data, "Cache-Control": "private, no-store" };
}

function privateNoStoreHeaders(): HeadersInit {
  return { "Cache-Control": "private, no-store" };
}

function invalidDocumentId(correlationId: string): Response {
  return webProblem(
    400,
    "WEB_INVALID_DOCUMENT_ID",
    "The document identifier is invalid.",
    "Start a new submission from the upload form.",
    correlationId,
  );
}

export async function proxyDocumentUpload(
  request: Request,
  accessToken: string,
  overrides: ProxyDependencyOverrides = {},
): Promise<Response> {
  const resolved = dependencies(overrides);
  const correlationId = requestCorrelationId(
    request,
    resolved.createCorrelationId,
  );
  let incoming: FormData;
  try {
    incoming = await request.formData();
  } catch {
    return webProblem(
      422,
      "WEB_INVALID_REQUEST",
      "A PDF file is required.",
      "Choose one PDF and submit it again.",
      correlationId,
    );
  }

  const file = incoming.get("file");
  if (!isFile(file)) {
    return webProblem(
      422,
      "WEB_INVALID_REQUEST",
      "A PDF file is required.",
      "Choose one PDF and submit it again.",
      correlationId,
    );
  }

  const outgoing = new FormData();
  outgoing.set("file", file, file.name);
  return callUpstream(
    request,
    accessToken,
    "/api/v1/documents",
    { method: "POST", body: outgoing },
    202,
    documentAcceptedSchema,
    overrides,
  );
}

export async function proxyDocumentStatus(
  request: Request,
  documentId: string,
  accessToken: string,
  overrides: ProxyDependencyOverrides = {},
): Promise<Response> {
  const resolved = dependencies(overrides);
  const correlationId = requestCorrelationId(
    request,
    resolved.createCorrelationId,
  );
  const parsedDocumentId = documentIdSchema.safeParse(documentId);
  if (!parsedDocumentId.success) {
    return invalidDocumentId(correlationId);
  }

  return callUpstream(
    request,
    accessToken,
    `/api/v1/documents/${parsedDocumentId.data}`,
    { method: "GET" },
    200,
    documentStatusSchema,
    overrides,
  );
}

export async function proxyDocumentReview(
  request: Request,
  documentId: string,
  accessToken: string,
  overrides: ProxyDependencyOverrides = {},
): Promise<Response> {
  const resolved = dependencies(overrides);
  const correlationId = requestCorrelationId(
    request,
    resolved.createCorrelationId,
  );
  const parsedDocumentId = documentIdSchema.safeParse(documentId);
  if (!parsedDocumentId.success) {
    return invalidDocumentId(correlationId);
  }
  return callUpstream(
    request,
    accessToken,
    `/api/v1/documents/${parsedDocumentId.data}/review`,
    { method: "GET" },
    200,
    reviewSchema,
    overrides,
    validatedReviewHeaders,
  );
}

export async function proxyDocumentReviewDecision(
  request: Request,
  documentId: string,
  accessToken: string,
  overrides: ProxyDependencyOverrides = {},
): Promise<Response> {
  const resolved = dependencies(overrides);
  const correlationId = requestCorrelationId(
    request,
    resolved.createCorrelationId,
  );
  const parsedDocumentId = documentIdSchema.safeParse(documentId);
  const entityTag = reviewEntityTagSchema.safeParse(
    request.headers.get("If-Match"),
  );
  const idempotencyKey = documentIdSchema.safeParse(
    request.headers.get("Idempotency-Key"),
  );
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    body = null;
  }
  const decision = reviewDecisionRequestSchema.safeParse(body);
  if (
    !parsedDocumentId.success ||
    !entityTag.success ||
    !idempotencyKey.success ||
    !decision.success
  ) {
    return webProblem(
      422,
      "WEB_INVALID_REVIEW_REQUEST",
      "The review request is invalid.",
      "Refresh the review and submit one supported final classification.",
      correlationId,
    );
  }
  return callUpstream(
    request,
    accessToken,
    `/api/v1/documents/${parsedDocumentId.data}/review`,
    {
      method: "PUT",
      headers: {
        "Content-Type": JSON_MEDIA_TYPE,
        "If-Match": entityTag.data,
        "Idempotency-Key": idempotencyKey.data,
      },
      body: JSON.stringify(decision.data),
    },
    200,
    terminalReviewSchema,
    overrides,
    validatedReviewHeaders,
  );
}

export async function proxyDocumentAuditHistory(
  request: Request,
  documentId: string,
  accessToken: string,
  overrides: ProxyDependencyOverrides = {},
): Promise<Response> {
  const resolved = dependencies(overrides);
  const correlationId = requestCorrelationId(
    request,
    resolved.createCorrelationId,
  );
  const parsedDocumentId = documentIdSchema.safeParse(documentId);
  if (!parsedDocumentId.success) {
    return invalidDocumentId(correlationId);
  }
  return callUpstream(
    request,
    accessToken,
    `/api/v1/documents/${parsedDocumentId.data}/audit-events`,
    { method: "GET" },
    200,
    auditHistorySchema,
    overrides,
    privateNoStoreHeaders,
  );
}

function bytesToHex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes), (value) =>
    value.toString(16).padStart(2, "0"),
  ).join("");
}

async function readBoundedBody(
  response: Response,
  maximumBytes: number,
): Promise<ArrayBuffer> {
  if (response.body === null) {
    throw new InvalidUpstreamResponseError();
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    total += value.byteLength;
    if (total > maximumBytes) {
      await reader.cancel().catch(() => undefined);
      throw new InvalidUpstreamResponseError();
    }
    chunks.push(value);
  }
  const content = new Uint8Array(new ArrayBuffer(total));
  let offset = 0;
  for (const chunk of chunks) {
    content.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return content.buffer;
}

export async function proxyDocumentSource(
  request: Request,
  documentId: string,
  accessToken: string,
  overrides: ProxyDependencyOverrides = {},
): Promise<Response> {
  const resolved = dependencies(overrides);
  const correlationId = requestCorrelationId(
    request,
    resolved.createCorrelationId,
  );
  const parsedDocumentId = documentIdSchema.safeParse(documentId);
  if (!parsedDocumentId.success) {
    return invalidDocumentId(correlationId);
  }

  try {
    const config = readServerConfig(resolved.environment);
    const response = await resolved.fetch(
      new URL(
        `/api/v1/documents/${parsedDocumentId.data}/source`,
        `${config.apiBaseUrl}/`,
      ),
      {
        method: "GET",
        headers: {
          Accept: `${PDF_MEDIA_TYPE}, ${PROBLEM_MEDIA_TYPE}`,
          Authorization: `Bearer ${accessToken}`,
          "X-Correlation-ID": correlationId,
        },
        signal: resolved.timeoutSignal(config.timeoutMilliseconds),
      },
    );
    if (!response.ok) {
      return await validatedUpstreamResponse(
        response,
        correlationId,
        200,
        documentStatusSchema,
      );
    }

    const upstreamCorrelation = response.headers.get("X-Correlation-ID");
    const contentLength = Number(response.headers.get("Content-Length"));
    const etag = response.headers.get("ETag");
    if (
      upstreamCorrelation !== correlationId ||
      mediaType(response) !== PDF_MEDIA_TYPE ||
      !Number.isSafeInteger(contentLength) ||
      contentLength < 1 ||
      contentLength > MAX_DOCUMENT_BYTES ||
      response.headers.get("Content-Disposition") !==
        'inline; filename="source.pdf"' ||
      response.headers.get("X-Content-Type-Options") !== "nosniff" ||
      etag === null ||
      !/^"[a-f0-9]{64}"$/.test(etag)
    ) {
      throw new InvalidUpstreamResponseError();
    }
    const content = await readBoundedBody(response, MAX_DOCUMENT_BYTES);
    if (content.byteLength !== contentLength) {
      throw new InvalidUpstreamResponseError();
    }
    const digest = bytesToHex(await crypto.subtle.digest("SHA-256", content));
    if (`"${digest}"` !== etag) {
      throw new InvalidUpstreamResponseError();
    }
    return new Response(content, {
      status: 200,
      headers: {
        "Content-Type": PDF_MEDIA_TYPE,
        "Content-Length": String(contentLength),
        "Content-Disposition": 'inline; filename="source.pdf"',
        "X-Content-Type-Options": "nosniff",
        ETag: etag,
        "X-Correlation-ID": correlationId,
        "Cache-Control": "private, no-store",
      },
    });
  } catch (error) {
    if (error instanceof InvalidUpstreamResponseError) {
      return webProblem(
        502,
        "WEB_INVALID_UPSTREAM_RESPONSE",
        "The processing service returned an invalid response.",
        "Please retry. If the problem continues, use the correlation ID when reporting it.",
        correlationId,
      );
    }
    return webProblem(
      503,
      "WEB_UPSTREAM_UNAVAILABLE",
      "The processing service is temporarily unavailable.",
      "Please wait a moment and try again.",
      correlationId,
    );
  }
}
