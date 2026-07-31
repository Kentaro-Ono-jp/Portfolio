import {
  finishSignIn,
  sanitizedAuthProblem,
  WebAuthenticationError,
} from "@/lib/web-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  try {
    return await finishSignIn(request);
  } catch (error) {
    if (error instanceof WebAuthenticationError) {
      return sanitizedAuthProblem(error);
    }
    return sanitizedAuthProblem(
      new WebAuthenticationError(
        503,
        "WEB_IDENTITY_UNAVAILABLE",
        "The identity service is temporarily unavailable.",
      ),
    );
  }
}
