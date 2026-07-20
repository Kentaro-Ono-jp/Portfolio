import { DocumentWorkflow } from "@/components/document-workflow";

export default function HomePage() {
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
            Submit one synthetic, single-page PDF. The API stores it, a durable
            queue hands it to a real PyTorch worker, and API-owned state returns
            the final classification.
          </p>
        </section>

        <div className="lg:sticky lg:top-12 lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <DocumentWorkflow />
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
            extractable text. No OCR, authentication, or production quality
            claim is implied.
          </p>
        </section>
      </div>
    </main>
  );
}
