// @vitest-environment node

import { beforeEach, describe, expect, it, vi } from "vitest";

import { proxyDocumentSource } from "@/lib/upstream-proxy";
import { requireWebSession, WebAuthenticationError } from "@/lib/web-auth";
import { DOCUMENT_ID } from "@/test/fixtures";

vi.mock("@/lib/upstream-proxy", () => ({
  proxyDocumentSource: vi.fn(),
}));
vi.mock("@/lib/web-auth", () => ({
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

import { dynamic, GET, runtime } from "./route";

describe("GET /api/documents/[documentId]/source", () => {
  beforeEach(() => {
    vi.mocked(proxyDocumentSource).mockReset();
    vi.mocked(requireWebSession).mockReset();
    vi.mocked(requireWebSession).mockResolvedValue({
      accessToken: "synthetic-access-token",
    } as never);
  });

  it("uses the server session token only on the private upstream hop", async () => {
    const expected = new Response("%PDF", {
      headers: { "Content-Type": "application/pdf" },
    });
    vi.mocked(proxyDocumentSource).mockResolvedValue(expected);
    const request = new Request(
      `http://web.test/api/documents/${DOCUMENT_ID}/source`,
    );

    await expect(
      GET(request, { params: Promise.resolve({ documentId: DOCUMENT_ID }) }),
    ).resolves.toBe(expected);
    expect(proxyDocumentSource).toHaveBeenCalledWith(
      request,
      DOCUMENT_ID,
      "synthetic-access-token",
    );
    expect(runtime).toBe("nodejs");
    expect(dynamic).toBe("force-dynamic");
  });

  it("sanitizes session and unexpected failures", async () => {
    const request = new Request(
      `http://web.test/api/documents/${DOCUMENT_ID}/source`,
    );
    const context = { params: Promise.resolve({ documentId: DOCUMENT_ID }) };
    vi.mocked(requireWebSession).mockRejectedValueOnce(
      new WebAuthenticationError(401, "WEB_SESSION_REQUIRED", "Required"),
    );
    expect((await GET(request, context)).status).toBe(401);
    vi.mocked(requireWebSession).mockRejectedValueOnce(new Error("private"));
    expect((await GET(request, context)).status).toBe(503);
  });
});
