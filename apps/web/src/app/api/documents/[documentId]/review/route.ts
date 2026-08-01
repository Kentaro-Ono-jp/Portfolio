import {
  proxyDocumentReview,
  proxyDocumentReviewDecision,
} from "@/lib/upstream-proxy";
import {
  requireCsrf,
  requireWebSession,
  sanitizedAuthProblem,
  WebAuthenticationError,
} from "@/lib/web-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface RouteContext {
  params: Promise<{ documentId: string }>;
}

function sessionFailure(error: unknown): Response {
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

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const { documentId } = await context.params;
  try {
    const session = await requireWebSession(request);
    return proxyDocumentReview(request, documentId, session.accessToken);
  } catch (error) {
    return sessionFailure(error);
  }
}

export async function PUT(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const { documentId } = await context.params;
  try {
    const session = await requireWebSession(request);
    requireCsrf(request, session);
    return proxyDocumentReviewDecision(
      request,
      documentId,
      session.accessToken,
    );
  } catch (error) {
    return sessionFailure(error);
  }
}
