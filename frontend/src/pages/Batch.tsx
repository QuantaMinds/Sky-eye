import { BatchReasonsBreakdown } from "@/components/BatchReasonsBreakdown"
import { BatchResultsTable } from "@/components/BatchResultsTable"
import { BatchStatusCounters } from "@/components/BatchStatusCounters"
import { BatchUploadForm } from "@/components/BatchUploadForm"
import { useBatchJob } from "@/hooks/useBatchJob"
import { getBatchExportUrl } from "@/lib/api-batch"

export function Batch() {
  const job = useBatchJob()

  const submitting = job.stage === "submitting" || job.stage === "polling"
  const showStatus = job.status !== null
  const showResults = job.stage === "complete" && job.status !== null
  const scoredCount = job.status?.completed_count ?? 0
  const canDownload = showResults && scoredCount > 0 && job.jobId !== null

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="mx-auto max-w-4xl px-4 pt-12 pb-6 space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Batch scoring</h1>
        <p className="text-sm text-muted-foreground">
          Upload up to 500 addresses. Each row is geocoded, parcel-resolved,
          and scored end-to-end. Multi-unit buildings are excluded from the
          ranking (different product category for C-46 residential).
        </p>
      </header>

      <section className="mx-auto max-w-4xl px-4 pb-8">
        <BatchUploadForm onSubmit={(addresses) => job.submit(addresses)} disabled={submitting} />
      </section>

      {job.stage === "submitting" && (
        <section className="mx-auto max-w-4xl px-4 pb-4" data-testid="stage-submitting">
          <p className="text-sm text-muted-foreground">Submitting batch…</p>
        </section>
      )}

      {job.error && (
        <section className="mx-auto max-w-4xl px-4 pb-4" role="alert">
          <p className="text-sm text-rose-600">{job.error}</p>
          <button onClick={job.reset} className="mt-2 text-sm underline">
            Try again
          </button>
        </section>
      )}

      {showStatus && job.status && (
        <section className="mx-auto max-w-4xl px-4 pb-6 space-y-6">
          <BatchStatusCounters status={job.status} />
          <BatchReasonsBreakdown
            skipReasons={job.status.skip_reasons}
            failureReasons={job.status.failure_reasons}
          />
        </section>
      )}

      {showResults && job.status && (
        <section className="mx-auto max-w-4xl px-4 pb-16">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Priority ranking
            </h2>
            {canDownload && job.jobId && (
              <a
                href={getBatchExportUrl(job.jobId)}
                download
                data-testid="batch-download-csv"
                className="inline-flex items-center rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground"
              >
                Download scored CSV ({scoredCount})
              </a>
            )}
          </div>
          <BatchResultsTable results={job.status.results} />
        </section>
      )}
    </main>
  )
}
