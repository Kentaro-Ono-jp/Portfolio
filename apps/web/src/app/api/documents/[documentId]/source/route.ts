import { proxyDocumentSource } from "@/lib/upstream-proxy";
import {
  requireWebSession,
  sanitizedAuthProblem,
  WebAuthenticationError,
} from "@/lib/web-auth";

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
  try {
    const session = await requireWebSession(request);
    return proxyDocumentSource(request, documentId, session.accessToken);
  } catch (error) {
    if (error instanceof WebAuthenticationError) {
      return sanitizedAuthProblem(error);
    }
    return sanitizedAuthProblem(
      new WebAuthenticationError(
        503,
        "WEB_SESSION_UNAVAILABLE",
        "The browser session is temporarily unavailable.",
      ),
    );
  }
}
