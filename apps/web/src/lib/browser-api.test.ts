import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createDocument,
  DocumentRequestError,
  getDocumentAuditHistory,
  getDocumentReview,
  getDocument,
  problemGuidance,
  submitDocumentReview,
  terminalFailureGuidance,
} from "@/lib/browser-api";
import {
  acceptedDocument,
  approvedReview,
  auditHistory,
  auditHistoryWithTimestamps,
  canonicalProblem,
  completedStatus,
  CORRELATION_ID,
  DOCUMENT_ID,
  REVIEW_ENTITY_TAG,
  unreviewedReview,
} from "@/test/fixtures";

function jsonResponse(body: unknown, status = 200, problem = false): Response {
  return Response.json(body, {
    status,
    headers: {
      "Content-Type": problem ? "application/problem+json" : "application/json",
      "X-Correlation-ID": CORRELATION_ID,
    },
  });
}

function reviewResponse(
  body: unknown,
  entityTag = REVIEW_ENTITY_TAG,
): Response {
  const response = jsonResponse(body);
  response.headers.set("ETag", entityTag);
  return response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("browser API client", () => {
  it("submits multipart data with a correlation identity", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(acceptedDocument, 202));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => CORRELATION_ID });
    const file = new File(["%PDF-1.7"], "invoice.pdf", {
      type: "application/pdf",
    });

    await expect(createDocument(file, "csrf-proof")).resolves.toEqual(
      acceptedDocument,
    );
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/documents");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("X-Correlation-ID")).toBe(
      CORRELATION_ID,
    );
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("csrf-proof");
    expect((init?.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("retrieves and validates terminal document state", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse(completedStatus));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => CORRELATION_ID });

    await expect(getDocument(DOCUMENT_ID)).resolves.toEqual(completedStatus);
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/documents/${DOCUMENT_ID}`,
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("retrieves review/audit evidence and submits a guarded decision", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(reviewResponse(unreviewedReview))
      .mockResolvedValueOnce(reviewResponse(approvedReview))
      .mockResolvedValueOnce(jsonResponse(auditHistory));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("crypto", { randomUUID: () => CORRELATION_ID });

    await expect(getDocumentReview(DOCUMENT_ID)).resolves.toEqual({
      review: unreviewedReview,
      entityTag: REVIEW_ENTITY_TAG,
    });
    const idempotencyKey = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    await expect(
      submitDocumentReview(
        DOCUMENT_ID,
        "invoice",
        REVIEW_ENTITY_TAG,
        idempotencyKey,
        "csrf-proof",
      ),
    ).resolves.toEqual({
      review: approvedReview,
      entityTag: REVIEW_ENTITY_TAG,
    });
    const decisionInit = fetchMock.mock.calls[1]![1];
    const decisionHeaders = new Headers(decisionInit?.headers);
    expect(decisionInit?.method).toBe("PUT");
    expect(decisionHeaders.get("If-Match")).toBe(REVIEW_ENTITY_TAG);
    expect(decisionHeaders.get("Idempotency-Key")).toBe(idempotencyKey);
    expect(decisionHeaders.get("X-CSRF-Token")).toBe("csrf-proof");
    expect(decisionInit?.body).toBe(
      JSON.stringify({ finalClassification: "invoice" }),
    );
    await expect(getDocumentAuditHistory(DOCUMENT_ID)).resolves.toEqual(
      auditHistory,
    );
  });

  it("rejects missing review entity tags and malformed audit ordering", async () => {
    vi.stubGlobal("crypto", { randomUUID: () => CORRELATION_ID });
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(unreviewedReview)),
    );
    await expect(getDocumentReview(DOCUMENT_ID)).rejects.toMatchObject({
      problem: { code: "WEB_INVALID_RESPONSE" },
    });

    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse({
          ...auditHistory,
          events: [...auditHistory.events].reverse(),
        }),
      ),
    );
    await expect(getDocumentAuditHistory(DOCUMENT_ID)).rejects.toMatchObject({
      problem: { code: "WEB_INVALID_RESPONSE" },
    });
  });

  it("normalizes offset audit chronology at the browser boundary", async () => {
    vi.stubGlobal("crypto", { randomUUID: () => CORRELATION_ID });
    const chronological = auditHistoryWithTimestamps(
      "2026-01-01T00:00:00Z",
      "2025-12-31T19:00:00.100000-05:00",
      "2026-01-01T01:00:01+01:00",
    );
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(chronological)),
    );
    await expect(getDocumentAuditHistory(DOCUMENT_ID)).resolves.toEqual(
      chronological,
    );

    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse({
          ...chronological,
          events: [
            chronological.events[1]!,
            chronological.events[0]!,
            chronological.events[2]!,
          ],
        }),
      ),
    );
    await expect(getDocumentAuditHistory(DOCUMENT_ID)).rejects.toMatchObject({
      problem: { code: "WEB_INVALID_RESPONSE" },
    });
  });

  it("throws a validated canonical problem", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(jsonResponse(canonicalProblem, 415, true)),
    );
    vi.stubGlobal("crypto", { randomUUID: () => CORRELATION_ID });

    await expect(getDocument(DOCUMENT_ID)).rejects.toMatchObject({
      name: "DocumentRequestError",
      problem: canonicalProblem,
    });
  });

  it("sanitizes network and malformed responses", async () => {
    vi.stubGlobal("crypto", { randomUUID: () => CORRELATION_ID });
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockRejectedValue(new Error("raw")),
    );
    await expect(getDocument(DOCUMENT_ID)).rejects.toMatchObject({
      problem: { code: "WEB_NETWORK_ERROR" },
    });

    const malformedResponses = [
      new Response("not-json", {
        status: 200,
        headers: { "X-Correlation-ID": CORRELATION_ID },
      }),
      jsonResponse({ ...completedStatus, confidence: 5 }),
      jsonResponse(completedStatus, 201),
      Response.json(completedStatus),
      new Response(JSON.stringify(completedStatus), {
        status: 200,
        headers: {
          "Content-Type": "text/plain",
          "X-Correlation-ID": CORRELATION_ID,
        },
      }),
      jsonResponse(canonicalProblem, 415, false),
      jsonResponse({ ...canonicalProblem, status: 400 }, 415, true),
      Response.json(canonicalProblem, {
        status: 415,
        headers: {
          "Content-Type": "application/problem+json",
          "X-Correlation-ID": DOCUMENT_ID,
        },
      }),
    ];
    for (const response of malformedResponses) {
      vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(response));
      await expect(getDocument(DOCUMENT_ID)).rejects.toMatchObject({
        problem: { code: "WEB_INVALID_RESPONSE" },
      });
    }
  });

  it("produces stable known and fallback guidance", () => {
    expect(problemGuidance(canonicalProblem)).toMatch(/application\/pdf/);
    expect(
      problemGuidance({ ...canonicalProblem, code: "SOMETHING_NEW" }),
    ).toContain("SOMETHING_NEW");
    expect(terminalFailureGuidance("SOURCE_DIGEST_MISMATCH")).toMatch(
      /integrity check/,
    );
    expect(terminalFailureGuidance("MODEL_FAILURE")).toContain("MODEL_FAILURE");
  });

  it("retains the public error type", () => {
    const error = new DocumentRequestError(canonicalProblem);
    expect(error.message).toBe(canonicalProblem.title);
    expect(error.problem).toBe(canonicalProblem);
  });
});
