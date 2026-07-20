export const MAX_PDF_BYTES = 5 * 1024 * 1024;

export function validatePdfFile(file: File | null): string | null {
  if (file === null) {
    return "Choose one PDF before submitting.";
  }
  if (file.type !== "application/pdf") {
    return "Choose a PDF with the application/pdf media type.";
  }
  if (file.size > MAX_PDF_BYTES) {
    return "Choose a PDF no larger than 5 MiB.";
  }
  return null;
}
