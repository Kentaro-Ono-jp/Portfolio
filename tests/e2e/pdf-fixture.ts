import { readFileSync } from "node:fs";

function escapePdfText(value: string): string {
  return value
    .replaceAll("\\", "\\\\")
    .replaceAll("(", "\\(")
    .replaceAll(")", "\\)");
}

function append(
  output: Buffer<ArrayBufferLike>,
  value: Buffer<ArrayBufferLike> | string,
): Buffer<ArrayBufferLike> {
  return Buffer.concat([
    output,
    typeof value === "string" ? Buffer.from(value, "ascii") : value,
  ]);
}

export function buildSinglePageTextPdf(text: string): Buffer<ArrayBufferLike> {
  const lines = text
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) {
    throw new Error("PDF fixture text must not be empty");
  }

  const commands = ["BT", "/F1 11 Tf", "72 760 Td"];
  lines.forEach((line, index) => {
    if (index > 0) {
      commands.push("0 -18 Td");
    }
    commands.push(`(${escapePdfText(line)}) Tj`);
  });
  commands.push("ET");
  const stream = Buffer.from(`${commands.join("\n")}\n`, "ascii");
  const objects = [
    Buffer.from("<< /Type /Catalog /Pages 2 0 R >>", "ascii"),
    Buffer.from("<< /Type /Pages /Kids [3 0 R] /Count 1 >>", "ascii"),
    Buffer.from(
      "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] " +
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
      "ascii",
    ),
    Buffer.from(
      "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
      "ascii",
    ),
    Buffer.concat([
      Buffer.from(`<< /Length ${stream.length} >>\nstream\n`, "ascii"),
      stream,
      Buffer.from("endstream", "ascii"),
    ]),
  ];

  let output: Buffer<ArrayBufferLike> = Buffer.from("%PDF-1.7\n%", "ascii");
  output = append(output, Buffer.from([0xe2, 0xe3, 0xcf, 0xd3]));
  output = append(output, "\n");
  const offsets = [0];
  objects.forEach((body, index) => {
    offsets.push(output.length);
    output = append(output, `${index + 1} 0 obj\n`);
    output = append(output, body);
    output = append(output, "\nendobj\n");
  });
  const xrefOffset = output.length;
  output = append(output, `xref\n0 ${objects.length + 1}\n`);
  output = append(output, "0000000000 65535 f \n");
  offsets.slice(1).forEach((offset) => {
    output = append(
      output,
      `${offset.toString().padStart(10, "0")} 00000 n \n`,
    );
  });
  output = append(
    output,
    `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\n` +
      `startxref\n${xrefOffset}\n%%EOF\n`,
  );
  return output;
}

export function canonicalInvoicePdf(): Buffer<ArrayBufferLike> {
  return buildSinglePageTextPdf(
    readFileSync("tests/fixtures/canonical_invoice.txt", "utf8"),
  );
}
