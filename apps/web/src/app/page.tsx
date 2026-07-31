import { cookies } from "next/headers";

import { DocumentWorkflow } from "@/components/document-workflow";
import { SessionControls } from "@/components/session-controls";
import { currentBrowserSession, SESSION_COOKIE } from "@/lib/web-auth";

export default async function HomePage() {
  const cookieStore = await cookies();
  const session = currentBrowserSession(cookieStore.get(SESSION_COOKIE)?.value);

  return (
    <main className="min-h-screen px-5 py-8 sm:px-8 lg:px-12 lg:py-12">
      <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(34rem,1.1fr)] lg:items-start">
        <section className="pt-3" aria-labelledby="page-title">
          <p className="eyebrow">ReactorFront / Document Intelligence</p>
          <h1
            id="page-title"
            className="mt-5 max-w-3xl text-5xl font-semibold tracking-[-0.055em] text-slate-950 sm:text-6xl lg:text-7xl"
          >
            From source PDF to a traceable ML result.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-600">
            Sign in as the synthetic reviewer and submit one single-page PDF.
            The API binds it to your stable principal, a durable queue hands it
            to a real PyTorch worker, and API-owned state returns the result.
          </p>
          {session === null ? null : (
            <SessionControls csrfToken={session.csrfToken} />
          )}
        </section>

        <div className="lg:sticky lg:top-12 lg:col-start-2 lg:row-span-2 lg:row-start-1">
          {session === null ? (
            <section className="workflow-shell px-6 py-8 sm:px-8">
              <p className="font-mono text-xs uppercase tracking-[0.18em] text-teal-700">
                Protected workflow
              </p>
              <h2 className="mt-3 text-2xl font-semibold text-slate-950">
                Sign in to classify a document
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                The deterministic Compose identity is synthetic and exists only
                for reproducible verification.
              </p>
              <a
                href="/api/auth/sign-in"
                className="mt-6 inline-flex min-h-12 items-center justify-center rounded-xl bg-teal-700 px-5 py-3 text-sm font-semibold text-white hover:bg-teal-800"
              >
                Sign in as synthetic reviewer
              </a>
            </section>
          ) : (
            <DocumentWorkflow csrfToken={session.csrfToken} />
          )}
        </div>

        <section
          className="lg:col-start-1 lg:row-start-2"
          aria-label="Workflow evidence"
        >
          <div className="grid gap-3 sm:grid-cols-3 lg:max-w-2xl">
            {[
              ["01", "Validated upload"],
              ["02", "Durable processing"],
              ["03", "Persisted result"],
            ].map(([number, label]) => (
              <div key={number} className="evidence-card">
                <span className="font-mono text-xs text-teal-700">
                  {number}
                </span>
                <span className="mt-3 block text-sm font-medium text-slate-800">
                  {label}
                </span>
              </div>
            ))}
          </div>

          <p className="mt-8 max-w-xl text-sm leading-6 text-slate-500">
            Scope is deliberately narrow: PDF only, up to 5 MiB, with
            extractable text and one synthetic reviewer. No OCR, production
            identity-provider, or production quality claim is implied.
          </p>
        </section>
      </div>
    </main>
  );
}
