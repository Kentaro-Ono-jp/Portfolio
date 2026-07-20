import type { z } from "zod";

import {
  correlationIdSchema,
  documentAcceptedSchema,
  documentIdSchema,
  documentStatusSchema,
  problemSchema,
  type Problem,
} from "@/lib/contracts";
import { readServerConfig } from "@/lib/server-config";

const JSON_MEDIA_TYPE = "application/json";
const PROBLEM_MEDIA_TYPE = "application/problem+json";

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
    return Response.json(parsed.data, {
      status: response.status,
      headers: { "X-Correlation-ID": upstreamCorrelation.data },
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
  path: string,
  init: RequestInit,
  successStatus: number,
  successSchema: z.ZodType<T>,
  overrides: ProxyDependencyOverrides,
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

export async function proxyDocumentUpload(
  request: Request,
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
  overrides: ProxyDependencyOverrides = {},
): Promise<Response> {
  const resolved = dependencies(overrides);
  const correlationId = requestCorrelationId(
    request,
    resolved.createCorrelationId,
  );
  const parsedDocumentId = documentIdSchema.safeParse(documentId);
  if (!parsedDocumentId.success) {
    return webProblem(
      400,
      "WEB_INVALID_DOCUMENT_ID",
      "The document identifier is invalid.",
      "Start a new submission from the upload form.",
      correlationId,
    );
  }

  return callUpstream(
    request,
    `/api/v1/documents/${parsedDocumentId.data}`,
    { method: "GET" },
    200,
    documentStatusSchema,
    overrides,
  );
}
