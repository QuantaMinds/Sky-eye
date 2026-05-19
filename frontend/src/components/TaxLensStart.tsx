import { useState, useEffect } from "react"

interface Props {
  onBack: () => void
}

export function TaxLensStart({ onBack }: Props) {
  const [stage, setStage] = useState<"idle" | "scanning" | "complete">("idle")

  useEffect(() => {
    if (stage === "scanning") {
      const t = setTimeout(() => {
        setStage("complete")
      }, 2000)
      return () => clearTimeout(t)
    }
  }, [stage])

  if (stage === "complete") {
    return (
      <div className="min-h-screen bg-background text-foreground animate-in fade-in duration-500">
        <header className="mx-auto max-w-5xl px-4 py-8">
          <button
            onClick={() => setStage("idle")}
            className="mb-8 text-sm font-medium text-muted-foreground hover:text-foreground inline-flex items-center gap-2 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Back to search
          </button>

          <div className="rounded-2xl border border-border bg-card p-6 md:p-8 shadow-sm">
            <h1 className="text-2xl font-bold tracking-tight">Long Beach</h1>
            <p className="text-sm text-muted-foreground mt-1">106,336 parcels scanned</p>
            <p className="text-sm text-muted-foreground">Compared imagery: May 2023 → April 2026</p>

            <div className="mt-8 space-y-3">
              <div className="flex items-center justify-between rounded-lg border border-primary/20 bg-primary/5 p-4 transition-colors hover:bg-primary/10">
                <div className="flex items-center gap-3">
                  <div className="h-3 w-3 rounded-full bg-rose-500"></div>
                  <span className="font-semibold">High confidence flags (&gt;80%)</span>
                </div>
                <div className="flex items-center gap-6">
                  <span className="font-mono text-sm text-muted-foreground">12 parcels</span>
                  <button className="text-sm font-medium text-primary hover:underline" onClick={() => alert("Mock: show table")}>Show me</button>
                </div>
              </div>

              <div className="flex items-center justify-between rounded-lg border border-border bg-transparent p-4 transition-colors hover:bg-muted/50">
                <div className="flex items-center gap-3">
                  <div className="h-3 w-3 rounded-full bg-amber-500"></div>
                  <span className="font-medium">Medium confidence (50-80%)</span>
                </div>
                <div className="flex items-center gap-6">
                  <span className="font-mono text-sm text-muted-foreground">38 parcels</span>
                  <button className="text-sm font-medium text-primary hover:underline" onClick={() => alert("Mock: show table")}>Show me</button>
                </div>
              </div>

              <div className="flex items-center justify-between rounded-lg border border-border bg-transparent p-4 opacity-70">
                <div className="flex items-center gap-3">
                  <div className="h-3 w-3 rounded-full bg-muted-foreground"></div>
                  <span className="text-muted-foreground">Low confidence (&lt;50%)</span>
                </div>
                <div className="flex items-center gap-6">
                  <span className="font-mono text-sm text-muted-foreground">117 parcels</span>
                  <span className="text-sm text-muted-foreground/50 pr-4">[hidden]</span>
                </div>
              </div>
            </div>
          </div>
        </header>
      </div>
    )
  }

  if (stage === "scanning") {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
        <div className="flex flex-col items-center space-y-4 animate-pulse">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
          <p className="text-sm font-medium text-muted-foreground">Scanning 106,336 residential parcels...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background text-foreground animate-in slide-in-from-right-8 fade-in duration-500 ease-out">
      <header className="mx-auto max-w-4xl px-4 py-8">
        <button
          onClick={onBack}
          className="text-sm font-medium text-muted-foreground hover:text-foreground inline-flex items-center gap-2 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          Back
        </button>
        <div className="mt-8 space-y-2">
          <h1 className="text-4xl font-extrabold tracking-tight">TaxLens</h1>
          <p className="text-lg text-muted-foreground">
            Find unpermitted construction across a city.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 pb-16 space-y-8">
        <section className="rounded-2xl border-2 border-primary/20 bg-card p-6 md:p-8 shadow-sm text-center space-y-6">
          <h2 className="text-xl font-bold tracking-tight">Ready to scan Long Beach?</h2>
          <p className="text-sm text-muted-foreground max-w-md mx-auto">
            This will compare May 2023 satellite imagery to April 2026 imagery across all 106,336 parcels to detect new structures, and cross-reference with the permit database.
          </p>
          <button
            onClick={() => setStage("scanning")}
            className="inline-flex items-center justify-center rounded-md bg-primary px-8 py-3 text-sm font-bold text-primary-foreground shadow transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            Start Citywide Scan
          </button>
        </section>
      </main>
    </div>
  )
}
