import { proxyDocumentUpload } from "@/lib/upstream-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  return proxyDocumentUpload(request);
}
