// @vitest-environment node

import { describe, expect, it, vi } from "vitest";

import {
  proxyDocumentStatus,
  proxyDocumentUpload,
  type ProxyDependencyOverrides,
} from "@/lib/upstream-proxy";
import {
  acceptedDocument,
  canonicalProblem,
  completedStatus,
  CORRELATION_ID,
  DOCUMENT_ID,
} from "@/test/fixtures";

function overrides(fetchMock: typeof fetch): ProxyDependencyOverrides {
  return {
    fetch: fetchMock,
    environment: {
      PORTFOLIO_API_BASE_URL: "http://api:8000",
      PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS: "1200",
    },
    createCorrelationId: () => CORRELATION_ID,
    timeoutSignal: () => new AbortController().signal,
  };
}

function upstreamJson(
  body: unknown,
  status: number,
  problem = false,
  correlationId = CORRELATION_ID,
): Response {
  return Response.json(body, {
    status,
    headers: {
      "Content-Type": problem ? "application/problem+json" : "application/json",
      "X-Correlation-ID": correlationId,
    },
  });
}

function uploadRequest(file: File): Request {
  const form = new FormData();
  form.set("file", file, file.name);
  return new Request("http://web.test/api/documents", {
    method: "POST",
    headers: { "X-Correlation-ID": CORRELATION_ID },
    body: form,
  });
}

describe("upstream document proxy", () => {
  it("forwards a PDF and validates the accepted response", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(upstreamJson(acceptedDocument, 202));
    const response = await proxyDocumentUpload(
      uploadRequest(
        new File(["%PDF-1.7"], "invoice.pdf", { type: "application/pdf" }),
      ),
      overrides(fetchMock),
    );

    expect(response.status).toBe(202);
    expect(await response.json()).toEqual(acceptedDocument);
    expect(response.headers.get("X-Correlation-ID")).toBe(CORRELATION_ID);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url.toString()).toBe("http://api:8000/api/v1/documents");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("X-Correlation-ID")).toBe(
      CORRELATION_ID,
    );
    expect((init?.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("preserves a canonical API problem and correlation identity", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(upstreamJson(canonicalProblem, 415, true));
    const response = await proxyDocumentUpload(
      uploadRequest(new File(["text"], "notes.txt", { type: "text/plain" })),
      overrides(fetchMock),
    );

    expect(response.status).toBe(415);
    expect(response.headers.get("Content-Type")).toContain(
      "application/problem+json",
    );
    expect(await response.json()).toEqual(canonicalProblem);
  });

  it("returns a stable local problem for missing or malformed multipart data", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    const emptyForm = new FormData();
    const missing = await proxyDocumentUpload(
      new Request("http://web.test/api/documents", {
        method: "POST",
        body: emptyForm,
      }),
      overrides(fetchMock),
    );
    const malformed = await proxyDocumentUpload(
      new Request("http://web.test/api/documents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      }),
      overrides(fetchMock),
    );

    expect(missing.status).toBe(422);
    expect((await missing.json()).code).toBe("WEB_INVALID_REQUEST");
    expect(malformed.status).toBe(422);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("validates a status response and rejects an invalid identifier locally", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(upstreamJson(completedStatus, 200));
    const request = new Request(`http://web.test/api/documents/${DOCUMENT_ID}`);
    const success = await proxyDocumentStatus(
      request,
      DOCUMENT_ID,
      overrides(fetchMock),
    );
    const invalid = await proxyDocumentStatus(
      request,
      "not-a-uuid",
      overrides(fetchMock),
    );

    expect(success.status).toBe(200);
    expect(await success.json()).toEqual(completedStatus);
    expect(fetchMock.mock.calls[0]![0].toString()).toBe(
      `http://api:8000/api/v1/documents/${DOCUMENT_ID}`,
    );
    expect(invalid.status).toBe(400);
    expect((await invalid.json()).code).toBe("WEB_INVALID_DOCUMENT_ID");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sanitizes configuration and network failures", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new Error("private"));
    const request = new Request(`http://web.test/api/documents/${DOCUMENT_ID}`);
    const network = await proxyDocumentStatus(
      request,
      DOCUMENT_ID,
      overrides(fetchMock),
    );
    const configuration = await proxyDocumentStatus(request, DOCUMENT_ID, {
      ...overrides(fetchMock),
      environment: {},
    });

    for (const response of [network, configuration]) {
      expect(response.status).toBe(503);
      const body = await response.json();
      expect(body.code).toBe("WEB_UPSTREAM_UNAVAILABLE");
      expect(JSON.stringify(body)).not.toContain("private");
    }
  });

  it("rejects malformed bodies, media types, statuses, and identities", async () => {
    const invalidResponses = [
      new Response("not json", {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "X-Correlation-ID": CORRELATION_ID,
        },
      }),
      upstreamJson({ ...completedStatus, confidence: 2 }, 200),
      new Response(JSON.stringify(completedStatus), {
        status: 200,
        headers: {
          "Content-Type": "text/plain",
          "X-Correlation-ID": CORRELATION_ID,
        },
      }),
      new Response(JSON.stringify(completedStatus), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
      upstreamJson(completedStatus, 201),
      upstreamJson(completedStatus, 200, false, DOCUMENT_ID),
      upstreamJson({ ...canonicalProblem, status: 400 }, 415, true),
      upstreamJson(
        { ...canonicalProblem, correlationId: DOCUMENT_ID },
        415,
        true,
      ),
      upstreamJson(
        { ...canonicalProblem, correlationId: DOCUMENT_ID },
        415,
        true,
        DOCUMENT_ID,
      ),
    ];

    for (const upstream of invalidResponses) {
      const response = await proxyDocumentStatus(
        new Request(`http://web.test/api/documents/${DOCUMENT_ID}`),
        DOCUMENT_ID,
        overrides(vi.fn<typeof fetch>().mockResolvedValue(upstream)),
      );
      expect(response.status).toBe(502);
      expect((await response.json()).code).toBe(
        "WEB_INVALID_UPSTREAM_RESPONSE",
      );
    }
  });
});
