import { proxyDocumentStatus } from "@/lib/upstream-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface RouteContext {
  params: Promise<{ documentId: string }>;
}

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const { documentId } = await context.params;
  return proxyDocumentStatus(request, documentId);
}
