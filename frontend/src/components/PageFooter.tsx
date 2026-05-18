interface Props {
  dataSources: string[]
  scoredAt?: string
  latencyMs?: number
}

function formatScoredAt(iso: string | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString()
}

export function PageFooter({ dataSources, scoredAt, latencyMs }: Props) {
  return (
    <footer
      data-testid="page-footer"
      className="border-t bg-muted/30 px-4 py-6 md:px-8 text-xs text-muted-foreground space-y-2"
    >
      <p>
        <span className="font-semibold">Data sources: </span>
        {dataSources.join(" · ")}
      </p>
      <p>
        Last scored: {formatScoredAt(scoredAt)}
        {typeof latencyMs === "number" && ` · ${latencyMs} ms`}
      </p>
    </footer>
  )
}
