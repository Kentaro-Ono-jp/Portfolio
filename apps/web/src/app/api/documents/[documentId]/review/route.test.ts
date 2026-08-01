// @vitest-environment node

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  proxyDocumentReview,
  proxyDocumentReviewDecision,
} from "@/lib/upstream-proxy";
import {
  requireCsrf,
  requireWebSession,
  WebAuthenticationError,
} from "@/lib/web-auth";
import { DOCUMENT_ID } from "@/test/fixtures";

vi.mock("@/lib/upstream-proxy", () => ({
  proxyDocumentReview: vi.fn(),
  proxyDocumentReviewDecision: vi.fn(),
}));
vi.mock("@/lib/web-auth", () => ({
  requireCsrf: vi.fn(),
  requireWebSession: vi.fn(),
  sanitizedAuthProblem: vi.fn((error: { status: number }) =>
    Response.json({}, { status: error.status }),
  ),
  WebAuthenticationError: class extends Error {
    constructor(
      readonly status: number,
      readonly code: string,
      message: string,
    ) {
      super(message);
    }
  },
}));

import { dynamic, GET, PUT, runtime } from "./route";

describe("/api/documents/[documentId]/review", () => {
  beforeEach(() => {
    vi.mocked(proxyDocumentReview).mockReset();
    vi.mocked(proxyDocumentReviewDecision).mockReset();
    vi.mocked(requireCsrf).mockReset();
    vi.mocked(requireWebSession).mockReset();
    vi.mocked(requireWebSession).mockResolvedValue({
      accessToken: "synthetic-access-token",
      csrfToken: "csrf-proof",
    } as never);
  });

  it("proxies authenticated reads and CSRF-protected decisions", async () => {
    const context = { params: Promise.resolve({ documentId: DOCUMENT_ID }) };
    const getRequest = new Request(
      `http://web.test/api/documents/${DOCUMENT_ID}/review`,
    );
    const putRequest = new Request(getRequest.url, { method: "PUT" });
    const getResponse = Response.json({ status: "get" });
    const putResponse = Response.json({ status: "put" });
    vi.mocked(proxyDocumentReview).mockResolvedValue(getResponse);
    vi.mocked(proxyDocumentReviewDecision).mockResolvedValue(putResponse);

    await expect(GET(getRequest, context)).resolves.toBe(getResponse);
    await expect(PUT(putRequest, context)).resolves.toBe(putResponse);
    expect(proxyDocumentReview).toHaveBeenCalledWith(
      getRequest,
      DOCUMENT_ID,
      "synthetic-access-token",
    );
    expect(requireCsrf).toHaveBeenCalledWith(
      putRequest,
      expect.objectContaining({ csrfToken: "csrf-proof" }),
    );
    expect(proxyDocumentReviewDecision).toHaveBeenCalledWith(
      putRequest,
      DOCUMENT_ID,
      "synthetic-access-token",
    );
    expect(runtime).toBe("nodejs");
    expect(dynamic).toBe("force-dynamic");
  });

  it("sanitizes authentication, CSRF, and unexpected failures", async () => {
    const request = new Request(
      "http://web.test/api/documents/not-a-uuid/review",
      {
        method: "PUT",
        body: JSON.stringify({ finalClassification: "unknown" }),
      },
    );
    const context = { params: Promise.resolve({ documentId: "not-a-uuid" }) };
    vi.mocked(requireWebSession).mockRejectedValueOnce(
      new WebAuthenticationError(401, "WEB_SESSION_REQUIRED", "Required"),
    );
    expect((await PUT(request, context)).status).toBe(401);
    expect(requireCsrf).not.toHaveBeenCalled();
    expect(proxyDocumentReviewDecision).not.toHaveBeenCalled();
    vi.mocked(requireCsrf).mockImplementationOnce(() => {
      throw new WebAuthenticationError(403, "WEB_CSRF_INVALID", "Invalid");
    });
    expect((await PUT(request, context)).status).toBe(403);
    expect(proxyDocumentReviewDecision).not.toHaveBeenCalled();
    vi.mocked(requireWebSession).mockRejectedValueOnce(new Error("private"));
    expect((await GET(request, context)).status).toBe(503);
    expect(proxyDocumentReview).not.toHaveBeenCalled();
  });
});
