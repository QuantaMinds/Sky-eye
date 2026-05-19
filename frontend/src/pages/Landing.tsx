import { Link } from "react-router-dom"
import { DemoCard } from "@/components/DemoCard"
import { DEMO_SCORES } from "@/lib/demo-data"

export function Landing() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <section className="mx-auto max-w-4xl px-4 py-16 text-center space-y-6">
        <h1 className="text-5xl font-bold tracking-tight">LeadLens</h1>
        <p className="mx-auto max-w-2xl text-lg text-muted-foreground">
          Solar lead scoring from public data — every claim verifiable against the LA County
          Assessor portal, Project Sunroof, and data.census.gov.
        </p>
        <div className="flex justify-center gap-3 pt-2">
          <Link
            to="/batch"
            className="inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Score a batch of addresses →
          </Link>
        </div>
        <p className="text-xs text-muted-foreground/70">
          Phase 2 demo. Live single-address scoring lands in Phase 3.
        </p>
      </section>

      <section className="mx-auto max-w-4xl px-4 pb-16">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Pre-scored examples
        </h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {DEMO_SCORES.map((s) => (
            <DemoCard key={s.apn} result={s} />
          ))}
        </div>
      </section>
    </main>
  )
}
