// @vitest-environment node

import { describe, expect, it, vi } from "vitest";
import { createHash } from "node:crypto";

import {
  proxyDocumentAuditHistory,
  proxyDocumentReview,
  proxyDocumentReviewDecision,
  proxyDocumentStatus,
  proxyDocumentSource,
  proxyDocumentUpload,
  type ProxyDependencyOverrides,
} from "@/lib/upstream-proxy";
import {
  acceptedDocument,
  approvedReview,
  auditHistory,
  canonicalProblem,
  completedStatus,
  CORRELATION_ID,
  DOCUMENT_ID,
  REVIEW_ENTITY_TAG,
  REVIEWER_PRINCIPAL_ID,
  unreviewedReview,
} from "@/test/fixtures";

const ACCESS_TOKEN = "synthetic-access-token";

function overrides(fetchMock: typeof fetch): ProxyDependencyOverrides {
  return {
    fetch: fetchMock,
    environment: {
      PORTFOLIO_API_BASE_URL: "http://api:8000",
      PORTFOLIO_WEB_UPSTREAM_TIMEOUT_MS: "1200",
      PORTFOLIO_WEB_PUBLIC_BASE_URL: "http://127.0.0.1:53000",
      PORTFOLIO_WEB_OIDC_ISSUER: "http://127.0.0.1:5556/dex",
      PORTFOLIO_WEB_OIDC_DISCOVERY_URL:
        "http://identity:5556/dex/.well-known/openid-configuration",
      PORTFOLIO_WEB_OIDC_TOKEN_URL: "http://identity:5556/dex/token",
      PORTFOLIO_WEB_OIDC_JWKS_URL: "http://identity:5556/dex/keys",
      PORTFOLIO_WEB_OIDC_CLIENT_ID: "reactorfront-api",
      PORTFOLIO_WEB_OIDC_ALLOW_INSECURE_LOOPBACK: "true",
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

function reviewUpstream(
  body: unknown,
  entityTag = REVIEW_ENTITY_TAG,
): Response {
  return Response.json(body, {
    headers: {
      "Content-Type": "application/json",
      "X-Correlation-ID": CORRELATION_ID,
      ETag: entityTag,
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
      ACCESS_TOKEN,
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
    expect(new Headers(init?.headers).get("Authorization")).toBe(
      `Bearer ${ACCESS_TOKEN}`,
    );
    expect((init?.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("preserves a canonical API problem and correlation identity", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValue(upstreamJson(canonicalProblem, 415, true));
    const response = await proxyDocumentUpload(
      uploadRequest(new File(["text"], "notes.txt", { type: "text/plain" })),
      ACCESS_TOKEN,
      overrides(fetchMock),
    );

    expect(response.status).toBe(415);
    expect(response.headers.get("Content-Type")).toContain(
      "application/problem+json",
    );
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
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
      ACCESS_TOKEN,
      overrides(fetchMock),
    );
    const malformed = await proxyDocumentUpload(
      new Request("http://web.test/api/documents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      }),
      ACCESS_TOKEN,
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
      ACCESS_TOKEN,
      overrides(fetchMock),
    );
    const invalid = await proxyDocumentStatus(
      request,
      "not-a-uuid",
      ACCESS_TOKEN,
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

  it("preserves review preconditions, idempotency, entity tags, and audit order", async () => {
    const reviewRead = await proxyDocumentReview(
      new Request(`http://web.test/api/documents/${DOCUMENT_ID}/review`),
      DOCUMENT_ID,
      ACCESS_TOKEN,
      overrides(
        vi
          .fn<typeof fetch>()
          .mockResolvedValue(reviewUpstream(unreviewedReview)),
      ),
    );
    expect(reviewRead.status).toBe(200);
    expect(reviewRead.headers.get("ETag")).toBe(REVIEW_ENTITY_TAG);
    expect(reviewRead.headers.get("Cache-Control")).toBe("private, no-store");

    const idempotencyKey = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    const putFetch = vi
      .fn<typeof fetch>()
      .mockResolvedValue(reviewUpstream(approvedReview));
    const decision = await proxyDocumentReviewDecision(
      new Request(`http://web.test/api/documents/${DOCUMENT_ID}/review`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "If-Match": REVIEW_ENTITY_TAG,
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify({ finalClassification: "invoice" }),
      }),
      DOCUMENT_ID,
      ACCESS_TOKEN,
      overrides(putFetch),
    );
    expect(decision.status).toBe(200);
    expect(decision.headers.get("ETag")).toBe(REVIEW_ENTITY_TAG);
    const [putUrl, putInit] = putFetch.mock.calls[0]!;
    expect(putUrl.toString()).toBe(
      `http://api:8000/api/v1/documents/${DOCUMENT_ID}/review`,
    );
    const putHeaders = new Headers(putInit?.headers);
    expect(putHeaders.get("If-Match")).toBe(REVIEW_ENTITY_TAG);
    expect(putHeaders.get("Idempotency-Key")).toBe(idempotencyKey);
    expect(putHeaders.get("Authorization")).toBe(`Bearer ${ACCESS_TOKEN}`);

    const audit = await proxyDocumentAuditHistory(
      new Request(`http://web.test/api/documents/${DOCUMENT_ID}/audit-events`),
      DOCUMENT_ID,
      ACCESS_TOKEN,
      overrides(
        vi
          .fn<typeof fetch>()
          .mockResolvedValue(upstreamJson(auditHistory, 200)),
      ),
    );
    expect(audit.status).toBe(200);
    expect(audit.headers.get("Cache-Control")).toBe("private, no-store");
    expect(await audit.json()).toEqual(auditHistory);
  });

  it("rejects malformed review mutations and unverified review evidence", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    const invalid = await proxyDocumentReviewDecision(
      new Request(`http://web.test/api/documents/${DOCUMENT_ID}/review`, {
        method: "PUT",
        headers: {
          "If-Match": "stale",
          "Idempotency-Key": "not-a-uuid",
        },
        body: JSON.stringify({ finalClassification: "unknown" }),
      }),
      DOCUMENT_ID,
      ACCESS_TOKEN,
      overrides(fetchMock),
    );
    expect(invalid.status).toBe(422);
    expect((await invalid.json()).code).toBe("WEB_INVALID_REVIEW_REQUEST");
    expect(fetchMock).not.toHaveBeenCalled();

    const actorLookingExtra = await proxyDocumentReviewDecision(
      new Request(`http://web.test/api/documents/${DOCUMENT_ID}/review`, {
        method: "PUT",
        headers: {
          "If-Match": REVIEW_ENTITY_TAG,
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({
          finalClassification: "invoice",
          reviewerPrincipalId: REVIEWER_PRINCIPAL_ID,
        }),
      }),
      DOCUMENT_ID,
      ACCESS_TOKEN,
      overrides(fetchMock),
    );
    expect(actorLookingExtra.status).toBe(422);
    expect((await actorLookingExtra.json()).code).toBe(
      "WEB_INVALID_REVIEW_REQUEST",
    );
    expect(fetchMock).not.toHaveBeenCalled();

    const missingEntityTag = await proxyDocumentReview(
      new Request(`http://web.test/api/documents/${DOCUMENT_ID}/review`),
      DOCUMENT_ID,
      ACCESS_TOKEN,
      overrides(
        vi
          .fn<typeof fetch>()
          .mockResolvedValue(upstreamJson(unreviewedReview, 200)),
      ),
    );
    expect(missingEntityTag.status).toBe(502);
    expect((await missingEntityTag.json()).code).toBe(
      "WEB_INVALID_UPSTREAM_RESPONSE",
    );

    const reversedAudit = {
      ...auditHistory,
      events: [...auditHistory.events].reverse(),
    };
    const invalidAudit = await proxyDocumentAuditHistory(
      new Request(`http://web.test/api/documents/${DOCUMENT_ID}/audit-events`),
      DOCUMENT_ID,
      ACCESS_TOKEN,
      overrides(
        vi
          .fn<typeof fetch>()
          .mockResolvedValue(upstreamJson(reversedAudit, 200)),
      ),
    );
    expect(invalidAudit.status).toBe(502);
  });

  it("sanitizes configuration and network failures", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValue(new Error("private"));
    const request = new Request(`http://web.test/api/documents/${DOCUMENT_ID}`);
    const network = await proxyDocumentStatus(
      request,
      DOCUMENT_ID,
      ACCESS_TOKEN,
      overrides(fetchMock),
    );
    const configuration = await proxyDocumentStatus(
      request,
      DOCUMENT_ID,
      ACCESS_TOKEN,
      {
        ...overrides(fetchMock),
        environment: {},
      },
    );

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
        ACCESS_TOKEN,
        overrides(vi.fn<typeof fetch>().mockResolvedValue(upstream)),
      );
      expect(response.status).toBe(502);
      expect((await response.json()).code).toBe(
        "WEB_INVALID_UPSTREAM_RESPONSE",
      );
    }
  });

  it("verifies the complete private source response before returning PDF bytes", async () => {
    const content = new TextEncoder().encode("%PDF-1.7 synthetic source");
    const digest = createHash("sha256").update(content).digest("hex");
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(content, {
        headers: {
          "Content-Type": "application/pdf",
          "Content-Length": String(content.byteLength),
          "Content-Disposition": 'inline; filename="source.pdf"',
          "X-Content-Type-Options": "nosniff",
          "X-Correlation-ID": CORRELATION_ID,
          ETag: `"${digest}"`,
        },
      }),
    );

    const response = await proxyDocumentSource(
      new Request(`http://web.test/api/documents/${DOCUMENT_ID}/source`),
      DOCUMENT_ID,
      ACCESS_TOKEN,
      overrides(fetchMock),
    );

    expect(response.status).toBe(200);
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(content);
    expect(response.headers.get("Cache-Control")).toBe("private, no-store");
    expect(
      new Headers(fetchMock.mock.calls[0]![1]?.headers).get("Authorization"),
    ).toBe(`Bearer ${ACCESS_TOKEN}`);
  });

  it("preserves source problems and rejects unverified source metadata", async () => {
    const problem = await proxyDocumentSource(
      new Request(`http://web.test/api/documents/${DOCUMENT_ID}/source`),
      DOCUMENT_ID,
      ACCESS_TOKEN,
      overrides(
        vi
          .fn<typeof fetch>()
          .mockResolvedValue(upstreamJson(canonicalProblem, 415, true)),
      ),
    );
    expect(problem.status).toBe(415);

    const invalid = await proxyDocumentSource(
      new Request(`http://web.test/api/documents/${DOCUMENT_ID}/source`),
      DOCUMENT_ID,
      ACCESS_TOKEN,
      overrides(
        vi.fn<typeof fetch>().mockResolvedValue(
          new Response("%PDF-invalid", {
            headers: {
              "Content-Type": "application/pdf",
              "Content-Length": "12",
              "Content-Disposition": 'inline; filename="source.pdf"',
              "X-Content-Type-Options": "nosniff",
              "X-Correlation-ID": CORRELATION_ID,
              ETag: `"${"0".repeat(64)}"`,
            },
          }),
        ),
      ),
    );
    expect(invalid.status).toBe(502);
    expect((await invalid.json()).code).toBe("WEB_INVALID_UPSTREAM_RESPONSE");

    const oversized = await proxyDocumentSource(
      new Request(`http://web.test/api/documents/${DOCUMENT_ID}/source`),
      DOCUMENT_ID,
      ACCESS_TOKEN,
      overrides(
        vi.fn<typeof fetch>().mockResolvedValue(
          new Response(new Uint8Array(5 * 1024 * 1024 + 1), {
            headers: {
              "Content-Type": "application/pdf",
              "Content-Length": "1",
              "Content-Disposition": 'inline; filename="source.pdf"',
              "X-Content-Type-Options": "nosniff",
              "X-Correlation-ID": CORRELATION_ID,
              ETag: `"${"0".repeat(64)}"`,
            },
          }),
        ),
      ),
    );
    expect(oversized.status).toBe(502);
  });
});
