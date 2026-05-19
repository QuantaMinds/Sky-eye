import { humanizeFailureReason, humanizeSkipReason } from "@/lib/format-batch"

interface Props {
  skipReasons?: Record<string, number> | null
  failureReasons?: Record<string, number> | null
}

/**
 * Humanized breakdown of the skip_reasons + failure_reasons dicts. Renders
 * nothing when both dicts are empty/null — truth-first: no empty section
 * headers implying buckets exist when they don't.
 *
 * Example output:
 *   Excluded
 *     · 55  Multi-unit buildings excluded (different product category)
 *   Failed
 *     · 7   Transient API errors (retryable)
 */
export function BatchReasonsBreakdown({ skipReasons, failureReasons }: Props) {
  const skipEntries = entriesByCountDesc(skipReasons)
  const failureEntries = entriesByCountDesc(failureReasons)
  if (skipEntries.length === 0 && failureEntries.length === 0) return null

  return (
    <div data-testid="batch-reasons-breakdown" className="space-y-4 text-sm">
      {skipEntries.length > 0 && (
        <Section title="Excluded" entries={skipEntries} humanize={humanizeSkipReason} testidPrefix="skip" />
      )}
      {failureEntries.length > 0 && (
        <Section title="Failed" entries={failureEntries} humanize={humanizeFailureReason} testidPrefix="failure" />
      )}
    </div>
  )
}

function entriesByCountDesc(d: Record<string, number> | null | undefined): [string, number][] {
  if (!d) return []
  return Object.entries(d).sort((a, b) => b[1] - a[1])
}

function Section({
  title, entries, humanize, testidPrefix,
}: {
  title: string
  entries: [string, number][]
  humanize: (k: string) => string
  testidPrefix: string
}) {
  return (
    <section>
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <ul className="space-y-1 pl-2">
        {entries.map(([key, count]) => (
          <li key={key} className="flex items-baseline gap-3" data-testid={`${testidPrefix}-row`} data-key={key}>
            <span className="w-10 text-right font-semibold tabular-nums">{count}</span>
            <span>{humanize(key)}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
