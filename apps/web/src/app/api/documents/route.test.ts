// @vitest-environment node

import { beforeEach, describe, expect, it, vi } from "vitest";

import { proxyDocumentUpload } from "@/lib/upstream-proxy";

vi.mock("@/lib/upstream-proxy", () => ({
  proxyDocumentUpload: vi.fn(),
}));

import { dynamic, POST, runtime } from "./route";

describe("POST /api/documents", () => {
  beforeEach(() => vi.mocked(proxyDocumentUpload).mockReset());

  it("uses the node runtime and delegates to the contract proxy", async () => {
    const expected = new Response(null, { status: 202 });
    vi.mocked(proxyDocumentUpload).mockResolvedValue(expected);
    const request = new Request("http://web.test/api/documents", {
      method: "POST",
    });

    await expect(POST(request)).resolves.toBe(expected);
    expect(proxyDocumentUpload).toHaveBeenCalledWith(request);
    expect(runtime).toBe("nodejs");
    expect(dynamic).toBe("force-dynamic");
  });
});
