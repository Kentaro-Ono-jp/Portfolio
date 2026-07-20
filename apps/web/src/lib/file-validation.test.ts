import { describe, expect, it } from "vitest";

import { MAX_PDF_BYTES, validatePdfFile } from "@/lib/file-validation";

describe("validatePdfFile", () => {
  it("requires one file", () => {
    expect(validatePdfFile(null)).toMatch(/Choose one PDF/);
  });

  it("requires the canonical media type", () => {
    const file = new File(["text"], "notes.txt", { type: "text/plain" });
    expect(validatePdfFile(file)).toMatch(/application\/pdf/);
  });

  it("enforces the five MiB boundary", () => {
    const file = new File([new Uint8Array(MAX_PDF_BYTES + 1)], "large.pdf", {
      type: "application/pdf",
    });
    expect(validatePdfFile(file)).toMatch(/5 MiB/);
  });

  it("accepts a supported PDF", () => {
    const file = new File(["%PDF-1.7"], "invoice.pdf", {
      type: "application/pdf",
    });
    expect(validatePdfFile(file)).toBeNull();
  });
});
