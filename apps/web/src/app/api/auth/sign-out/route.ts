import {
  sanitizedAuthProblem,
  signOut,
  WebAuthenticationError,
} from "@/lib/web-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  try {
    return signOut(request);
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
