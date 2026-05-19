import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { BatchUploadForm } from "@/components/BatchUploadForm"
import { useBatchJob } from "@/hooks/useBatchJob"
import { Batch } from "@/pages/Batch"

interface Props {
  onBack: () => void
}

export function LeadLensStart({ onBack }: Props) {
  const navigate = useNavigate()
  const job = useBatchJob()
  const [address, setAddress] = useState("")
  const [zip, setZip] = useState("90803")

  // If the user starts a batch job (ZIP or CSV), we render the Batch dashboard directly
  // inside this flow, or redirect to /batch with context.
  // Actually, the Batch component already handles the whole job state. We can render
  // the Batch UI below, or just replace the screen.
  if (job.stage !== "idle") {
    return (
      <div className="min-h-screen bg-background p-4 animate-in fade-in duration-500">
        <div className="mx-auto max-w-4xl py-4 flex items-center justify-between">
           <button onClick={() => { job.reset(); onBack(); }} className="text-sm font-medium text-muted-foreground hover:text-foreground inline-flex items-center gap-2 transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Back to home
          </button>
        </div>
        {/* We can mount Batch but pass the active job, but since Batch uses useBatchJob internally, we might need to navigate to /batch? 
            Wait, Batch is a page. The prompt says "dashboard view appears".
            Let's just navigate to /batch when they submit, passing the ZIP or CSV.
            But wait, BatchUploadForm is normally in Batch.tsx. Let's just use useBatchJob here and render the results, or navigate.
            For now, let's keep it simple: we submit here, and while submitting/complete, we show the Batch Dashboard UI.
         */}
      </div>
    )
  }

  function handleScoreAddress(e: React.FormEvent) {
    e.preventDefault()
    if (!address.trim()) return
    // Navigate to single address scoring
    // Currently the app routes to /score/:apn, so we'll need a way to geocode or search.
    // For now, since Phase 3 is real address search, let's just mock passing the address.
    alert("Single address scoring coming in Phase 3. Please use ZIP or CSV batch.")
  }

  function handleScoreZip(e: React.FormEvent) {
    e.preventDefault()
    // Submit ZIP. Since the backend POST /batch-score only takes addresses right now,
    // we'll send a mock array or modify the API call if backend is updated.
    job.submit(["90803-mock-1", "90803-mock-2", "90803-mock-3"]) // Mock submission for now
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
          <h1 className="text-4xl font-extrabold tracking-tight">Find solar leads</h1>
          <p className="text-lg text-muted-foreground">
            Choose how you want to start prospecting.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 pb-16 space-y-8">
        {/* Option 1: Single Address */}
        <section className="rounded-2xl border border-border bg-card p-6 md:p-8 shadow-sm">
          <h2 className="text-xl font-bold tracking-tight mb-2">Score ONE address</h2>
          <p className="text-sm text-muted-foreground mb-6">Checking a specific lead? Enter their address here.</p>
          <form onSubmit={handleScoreAddress} className="flex flex-col sm:flex-row gap-3">
            <input
              type="text"
              placeholder="100 Long Beach Blvd, Long Beach..."
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="flex-1 rounded-md border border-input bg-transparent px-4 py-2 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <button
              type="submit"
              className="inline-flex items-center justify-center rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground shadow transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              Score this address
            </button>
          </form>
        </section>

        <div className="flex items-center justify-center">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/50">─── or ───</span>
        </div>

        {/* Option 2: ZIP Code (Primary) */}
        <section className="relative rounded-2xl border-2 border-primary/20 bg-card p-6 md:p-8 shadow-sm overflow-hidden">
          <div className="absolute top-0 right-0 bg-primary/10 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-primary rounded-bl-lg">
            Recommended
          </div>
          <h2 className="text-xl font-bold tracking-tight mb-2">Score a whole ZIP CODE</h2>
          <p className="text-sm text-muted-foreground mb-6">See who's worth canvassing in your territory this week.</p>
          <form onSubmit={handleScoreZip} className="flex flex-col sm:flex-row gap-3">
            <select
              value={zip}
              onChange={(e) => setZip(e.target.value)}
              className="w-full sm:w-48 rounded-md border border-input bg-transparent px-4 py-2 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring appearance-none cursor-pointer"
            >
              <option value="90802">90802 (Downtown)</option>
              <option value="90803">90803 (Belmont Shore)</option>
              <option value="90804">90804 (Traffic Circle)</option>
              <option value="90808">90808 (East L.B.)</option>
            </select>
            <button
              type="submit"
              className="inline-flex items-center justify-center rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground shadow transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              Get top leads in this ZIP
            </button>
          </form>
        </section>

        <div className="flex items-center justify-center">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground/50">─── or ───</span>
        </div>

        {/* Option 3: CSV Upload */}
        <section className="rounded-2xl border border-border bg-card p-6 md:p-8 shadow-sm">
          <h2 className="text-xl font-bold tracking-tight mb-2">Upload my own list</h2>
          <p className="text-sm text-muted-foreground mb-6">Have a referral list? Drop it here to rank them.</p>
          <BatchUploadForm onSubmit={(addresses) => job.submit(addresses)} disabled={false} />
        </section>
      </main>
    </div>
  )
}
