import { useState } from "react"
import { LeadLensStart } from "@/components/LeadLensStart"
import { TaxLensStart } from "@/components/TaxLensStart"

export function Landing() {
  const [productPath, setProductPath] = useState<"leadlens" | "taxlens" | null>(null)

  if (productPath === "leadlens") {
    return <LeadLensStart onBack={() => setProductPath(null)} />
  }

  if (productPath === "taxlens") {
    return <TaxLensStart onBack={() => setProductPath(null)} />
  }

  return (
    <main className="min-h-screen bg-background text-foreground flex flex-col items-center justify-center p-4 selection:bg-primary selection:text-primary-foreground">
      <div className="w-full max-w-4xl mx-auto text-center space-y-12 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-out">
        <div className="space-y-4">
          <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight text-primary">
            What are you here to do?
          </h1>
          <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto font-medium">
            Select a product path to begin your search.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 md:gap-8 max-w-3xl mx-auto">
          <button
            onClick={() => setProductPath("leadlens")}
            className="group relative overflow-hidden rounded-2xl border-2 border-border bg-card p-8 text-left transition-all hover:-translate-y-1 hover:shadow-[0_8px_30px_rgb(0,0,0,0.06)] hover:border-primary/30 dark:hover:shadow-[0_8px_30px_rgb(255,255,255,0.06)]"
          >
            <div className="space-y-4">
              <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary group-hover:scale-110 transition-transform duration-300">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              </div>
              <div>
                <h2 className="text-2xl font-bold tracking-tight mb-2 group-hover:text-primary transition-colors">
                  Find solar leads
                </h2>
                <p className="text-muted-foreground">
                  Score and rank residential parcels for solar viability using the LeadLens engine.
                </p>
              </div>
            </div>
            <div className="absolute top-8 right-8 text-muted-foreground/30 opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </button>

          <button
            onClick={() => setProductPath("taxlens")}
            className="group relative overflow-hidden rounded-2xl border-2 border-border bg-card p-8 text-left transition-all hover:-translate-y-1 hover:shadow-[0_8px_30px_rgb(0,0,0,0.06)] hover:border-primary/30 dark:hover:shadow-[0_8px_30px_rgb(255,255,255,0.06)]"
          >
            <div className="space-y-4">
              <div className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary group-hover:scale-110 transition-transform duration-300">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
              </div>
              <div>
                <h2 className="text-2xl font-bold tracking-tight mb-2 group-hover:text-primary transition-colors">
                  Find unpermitted construction
                </h2>
                <p className="text-muted-foreground">
                  Detect high-confidence, unpermitted structural additions using the TaxLens engine.
                </p>
              </div>
            </div>
            <div className="absolute top-8 right-8 text-muted-foreground/30 opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </button>
        </div>
      </div>
    </main>
  )
}
