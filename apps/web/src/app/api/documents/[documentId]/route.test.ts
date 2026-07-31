// @vitest-environment node

import { beforeEach, describe, expect, it, vi } from "vitest";

import { proxyDocumentStatus } from "@/lib/upstream-proxy";
import { requireWebSession, WebAuthenticationError } from "@/lib/web-auth";
import { DOCUMENT_ID } from "@/test/fixtures";

vi.mock("@/lib/upstream-proxy", () => ({
  proxyDocumentStatus: vi.fn(),
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

describe("GET /api/documents/[documentId]", () => {
  beforeEach(() => {
    vi.mocked(proxyDocumentStatus).mockReset();
    vi.mocked(requireWebSession).mockReset();
    vi.mocked(requireWebSession).mockResolvedValue({
      accessToken: "synthetic-access-token",
    } as never);
  });

  it("awaits route parameters and delegates to the contract proxy", async () => {
    const expected = Response.json({ status: "ok" });
    vi.mocked(proxyDocumentStatus).mockResolvedValue(expected);
    const request = new Request(`http://web.test/api/documents/${DOCUMENT_ID}`);

    await expect(
      GET(request, { params: Promise.resolve({ documentId: DOCUMENT_ID }) }),
    ).resolves.toBe(expected);
    expect(proxyDocumentStatus).toHaveBeenCalledWith(
      request,
      DOCUMENT_ID,
      "synthetic-access-token",
    );
    expect(runtime).toBe("nodejs");
    expect(dynamic).toBe("force-dynamic");
  });

  it("sanitizes session and unexpected failures", async () => {
    const request = new Request(`http://web.test/api/documents/${DOCUMENT_ID}`);
    const context = { params: Promise.resolve({ documentId: DOCUMENT_ID }) };
    vi.mocked(requireWebSession).mockRejectedValueOnce(
      new WebAuthenticationError(401, "WEB_SESSION_REQUIRED", "Required"),
    );
    expect((await GET(request, context)).status).toBe(401);
    vi.mocked(requireWebSession).mockRejectedValueOnce(new Error("private"));
    expect((await GET(request, context)).status).toBe(503);
  });
});
