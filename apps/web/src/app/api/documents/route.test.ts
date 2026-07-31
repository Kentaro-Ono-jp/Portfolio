// @vitest-environment node

import { beforeEach, describe, expect, it, vi } from "vitest";

import { proxyDocumentUpload } from "@/lib/upstream-proxy";
import {
  requireCsrf,
  requireWebSession,
  WebAuthenticationError,
} from "@/lib/web-auth";

vi.mock("@/lib/upstream-proxy", () => ({
  proxyDocumentUpload: vi.fn(),
}));
vi.mock("@/lib/web-auth", () => ({
  requireWebSession: vi.fn(),
  requireCsrf: vi.fn(),
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

import { dynamic, POST, runtime } from "./route";

describe("POST /api/documents", () => {
  beforeEach(() => {
    vi.mocked(proxyDocumentUpload).mockReset();
    vi.mocked(requireCsrf).mockReset();
    vi.mocked(requireWebSession).mockReset();
    vi.mocked(requireWebSession).mockResolvedValue({
      accessToken: "synthetic-access-token",
    } as never);
  });

  it("uses the node runtime and delegates to the contract proxy", async () => {
    const expected = new Response(null, { status: 202 });
    vi.mocked(proxyDocumentUpload).mockResolvedValue(expected);
    const request = new Request("http://web.test/api/documents", {
      method: "POST",
    });

    await expect(POST(request)).resolves.toBe(expected);
    expect(requireCsrf).toHaveBeenCalled();
    expect(proxyDocumentUpload).toHaveBeenCalledWith(
      request,
      "synthetic-access-token",
    );
    expect(runtime).toBe("nodejs");
    expect(dynamic).toBe("force-dynamic");
  });

  it("sanitizes session and unexpected failures before proxying", async () => {
    const request = new Request("http://web.test/api/documents", {
      method: "POST",
    });
    vi.mocked(requireWebSession).mockRejectedValueOnce(
      new WebAuthenticationError(401, "WEB_SESSION_REQUIRED", "Required"),
    );
    expect((await POST(request)).status).toBe(401);
    vi.mocked(requireWebSession).mockRejectedValueOnce(new Error("private"));
    expect((await POST(request)).status).toBe(503);
    expect(proxyDocumentUpload).not.toHaveBeenCalled();
  });
});
