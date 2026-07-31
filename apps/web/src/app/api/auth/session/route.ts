import {
  requireWebSession,
  sanitizedAuthProblem,
  WebAuthenticationError,
} from "@/lib/web-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  try {
    const session = await requireWebSession(request);
    return Response.json(
      {
        authenticated: true,
        csrfToken: session.csrfToken,
        expiresAt: new Date(session.absoluteExpiresAt).toISOString(),
      },
      { headers: { "Cache-Control": "no-store" } },
    );
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
