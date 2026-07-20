import type { z } from "zod";

import {
  correlationIdSchema,
  documentAcceptedSchema,
  documentStatusSchema,
  problemSchema,
  type DocumentAccepted,
  type DocumentStatus,
  type Problem,
} from "@/lib/contracts";

const JSON_MEDIA_TYPE = "application/json";
const PROBLEM_MEDIA_TYPE = "application/problem+json";

export class DocumentRequestError extends Error {
  readonly problem: Problem;

  constructor(problem: Problem) {
    super(problem.title);
    this.name = "DocumentRequestError";
    this.problem = problem;
  }
}

function fallbackCorrelationId(response?: Response): string {
  const candidate = response?.headers.get("X-Correlation-ID");
  const parsed = correlationIdSchema.safeParse(candidate);
  return parsed.success ? parsed.data : crypto.randomUUID();
}

function clientProblem(
  code: string,
  title: string,
  detail: string,
  response?: Response,
): DocumentRequestError {
  return new DocumentRequestError({
    type: `/problems/${code.toLowerCase().replaceAll("_", "-")}`,
    title,
    status: response?.status && response.status >= 400 ? response.status : 503,
    code,
    detail,
    correlationId: fallbackCorrelationId(response),
  });
}

async function requestJson<T>(
  input: RequestInfo | URL,
  init: RequestInit,
  successStatus: number,
  schema: z.ZodType<T>,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(input, init);
  } catch {
    throw clientProblem(
      "WEB_NETWORK_ERROR",
      "The request could not reach the Web service.",
      "Check your connection and try again.",
    );
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw clientProblem(
      "WEB_INVALID_RESPONSE",
      "The Web service returned an invalid response.",
      "Please retry the request.",
      response,
    );
  }

  const responseMediaType =
    response.headers.get("Content-Type")?.split(";", 1)[0]?.trim() ?? "";
  const responseCorrelation = correlationIdSchema.safeParse(
    response.headers.get("X-Correlation-ID"),
  );

  if (!response.ok) {
    const parsedProblem = problemSchema.safeParse(payload);
    if (
      responseMediaType !== PROBLEM_MEDIA_TYPE ||
      !responseCorrelation.success ||
      !parsedProblem.success ||
      parsedProblem.data.status !== response.status ||
      parsedProblem.data.correlationId !== responseCorrelation.data
    ) {
      throw clientProblem(
        "WEB_INVALID_RESPONSE",
        "The Web service returned an invalid response.",
        "Please retry the request.",
        response,
      );
    }
    throw new DocumentRequestError(parsedProblem.data);
  }

  if (
    response.status !== successStatus ||
    responseMediaType !== JSON_MEDIA_TYPE ||
    !responseCorrelation.success
  ) {
    throw clientProblem(
      "WEB_INVALID_RESPONSE",
      "The Web service returned an invalid response.",
      "Please retry the request.",
      response,
    );
  }

  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw clientProblem(
      "WEB_INVALID_RESPONSE",
      "The Web service returned an invalid response.",
      "Please retry the request.",
      response,
    );
  }
  return parsed.data;
}

export async function createDocument(file: File): Promise<DocumentAccepted> {
  const form = new FormData();
  form.set("file", file, file.name);
  return requestJson(
    "/api/documents",
    {
      method: "POST",
      headers: { "X-Correlation-ID": crypto.randomUUID() },
      body: form,
    },
    202,
    documentAcceptedSchema,
  );
}

export async function getDocument(documentId: string): Promise<DocumentStatus> {
  return requestJson(
    `/api/documents/${encodeURIComponent(documentId)}`,
    {
      method: "GET",
      headers: { "X-Correlation-ID": crypto.randomUUID() },
    },
    200,
    documentStatusSchema,
  );
}

const PROBLEM_GUIDANCE: Readonly<Record<string, string>> = {
  INVALID_DOCUMENT: "The selected file is not a supported PDF.",
  DOCUMENT_TOO_LARGE: "The selected PDF is larger than 5 MiB.",
  UNSUPPORTED_MEDIA_TYPE: "Choose a PDF with the application/pdf media type.",
  DEPENDENCY_UNAVAILABLE:
    "The processing service is unavailable. Please retry shortly.",
  WEB_UPSTREAM_UNAVAILABLE:
    "The processing service is unavailable. Please retry shortly.",
  WEB_NETWORK_ERROR:
    "The request could not be sent. Check your connection and retry.",
};

export function problemGuidance(problem: Problem): string {
  return (
    PROBLEM_GUIDANCE[problem.code] ??
    `The request could not be completed (${problem.code}). Please try again.`
  );
}

export function terminalFailureGuidance(failureCode: string): string {
  if (failureCode === "SOURCE_DIGEST_MISMATCH") {
    return "The uploaded source failed its integrity check. Submit the PDF again.";
  }
  return `Processing stopped safely (${failureCode}). Submit the PDF again.`;
}
