// @vitest-environment node

import { beforeEach, describe, expect, it, vi } from "vitest";

import { proxyDocumentStatus } from "@/lib/upstream-proxy";
import { DOCUMENT_ID } from "@/test/fixtures";

vi.mock("@/lib/upstream-proxy", () => ({
  proxyDocumentStatus: vi.fn(),
}));

import { dynamic, GET, runtime } from "./route";

describe("GET /api/documents/[documentId]", () => {
  beforeEach(() => vi.mocked(proxyDocumentStatus).mockReset());

  it("awaits route parameters and delegates to the contract proxy", async () => {
    const expected = Response.json({ status: "ok" });
    vi.mocked(proxyDocumentStatus).mockResolvedValue(expected);
    const request = new Request(`http://web.test/api/documents/${DOCUMENT_ID}`);

    await expect(
      GET(request, { params: Promise.resolve({ documentId: DOCUMENT_ID }) }),
    ).resolves.toBe(expected);
    expect(proxyDocumentStatus).toHaveBeenCalledWith(request, DOCUMENT_ID);
    expect(runtime).toBe("nodejs");
    expect(dynamic).toBe("force-dynamic");
  });
});
