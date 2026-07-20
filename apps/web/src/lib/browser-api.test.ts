import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createDocument,
  DocumentRequestError,
  getDocument,
  problemGuidance,
  terminalFailureGuidance,
} from "@/lib/browser-api";
import {
  acceptedDocument,
  canonicalProblem,
  completedStatus,
  CORRELATION_ID,
  DOCUMENT_ID,
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

    await expect(createDocument(file)).resolves.toEqual(acceptedDocument);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/documents");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("X-Correlation-ID")).toBe(
      CORRELATION_ID,
    );
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
