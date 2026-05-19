import { useState } from "react"
import { parseCsvAddresses, readFileAsText } from "@/lib/csv"

interface Props {
  onSubmit: (addresses: string[]) => void | Promise<void>
  disabled?: boolean
}

export function BatchUploadForm({ onSubmit, disabled = false }: Props) {
  const [text, setText] = useState("")
  const [fileName, setFileName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const parsed = parseCsvAddresses(text)
  const count = parsed.addresses.length
  const tooMany = count >= 500 // backend cap; parser already truncates

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    setError(null)
    setFileName(f.name)
    try {
      setText(await readFileAsText(f))
    } catch {
      setError("Could not read file.")
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (count === 0) {
      setError("Paste or upload at least one address.")
      return
    }
    setError(null)
    await onSubmit(parsed.addresses)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" aria-label="Batch upload form">
      <div className="space-y-1">
        <label className="block text-sm font-medium" htmlFor="batch-file">
          CSV file (one address per row, first column used)
        </label>
        <input
          id="batch-file"
          type="file"
          accept=".csv,text/csv,text/plain"
          onChange={handleFile}
          disabled={disabled}
          className="block text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-1.5 file:text-primary-foreground"
        />
        {fileName && (
          <p className="text-xs text-muted-foreground">Loaded: {fileName}</p>
        )}
      </div>
      <div className="space-y-1">
        <label className="block text-sm font-medium" htmlFor="batch-paste">
          Or paste addresses (one per line)
        </label>
        <textarea
          id="batch-paste"
          rows={6}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={disabled}
          placeholder={"100 Long Beach Blvd, Long Beach, CA 90802\n200 Pine Ave, Long Beach, CA 90802"}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        />
      </div>
      <div className="flex items-center justify-between text-sm">
        <span data-testid="batch-upload-summary" className="text-muted-foreground">
          {count} address{count === 1 ? "" : "es"}
          {parsed.duplicateCount > 0 && ` · ${parsed.duplicateCount} duplicate${parsed.duplicateCount === 1 ? "" : "s"} removed`}
          {tooMany && " · capped at 500"}
        </span>
        <button
          type="submit"
          disabled={disabled || count === 0}
          className="inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          Score batch
        </button>
      </div>
      {error && <p role="alert" className="text-sm text-rose-600">{error}</p>}
    </form>
  )
}
