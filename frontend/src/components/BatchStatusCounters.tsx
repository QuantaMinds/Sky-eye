import type { BatchStatusResponse } from "@/types/batch"

interface Props {
  status: BatchStatusResponse
}

/**
 * Headline counter tree:
 *   100 addresses uploaded
 *   ├── 38 scored as priority leads
 *   ├── 55 excluded (multi-unit or different product category)
 *   └──  7 failed (transient errors, retryable)
 *
 * Truth-first: every number comes from the BatchStatusResponse counters,
 * never inferred or computed from the results list. The invariant
 * address_count == completed + skipped + failed is asserted visually:
 * if the sum doesn't match, a small warning row appears so the
 * conflation bug surfaces instead of hiding.
 */
export function BatchStatusCounters({ status }: Props) {
  const { address_count, completed_count, skipped_count, failed_count } = status
  const sum = completed_count + skipped_count + failed_count
  const mismatch = status.status === "complete" && sum !== address_count

  return (
    <div data-testid="batch-status-counters" className="space-y-2 text-sm">
      <div className="font-medium">
        <span data-testid="counter-total" className="tabular-nums">
          {address_count}
        </span>{" "}
        address{address_count === 1 ? "" : "es"} uploaded
      </div>
      <ul className="space-y-1 pl-4">
        <Row label="scored as priority leads" count={completed_count} tier="ok"
             testid="counter-completed" />
        <Row label="excluded (different product category)" count={skipped_count} tier="muted"
             testid="counter-skipped" />
        <Row label="failed (transient errors, retryable)" count={failed_count} tier="warn"
             testid="counter-failed" />
      </ul>
      {mismatch && (
        <p role="alert" className="text-xs text-rose-600">
          Counter invariant broken: {completed_count} + {skipped_count} + {failed_count}{" "}
          ≠ {address_count}. Report this — a row escaped the bucketing rules.
        </p>
      )}
    </div>
  )
}

const TIER_DOT = {
  ok: "bg-emerald-500",
  muted: "bg-slate-400",
  warn: "bg-amber-500",
} as const

function Row({
  label, count, tier, testid,
}: {
  label: string
  count: number
  tier: keyof typeof TIER_DOT
  testid: string
}) {
  return (
    <li className="flex items-center gap-3">
      <span className={`inline-block h-2 w-2 rounded-full ${TIER_DOT[tier]}`} />
      <span data-testid={testid} className="font-semibold tabular-nums w-10 text-right">
        {count}
      </span>
      <span className="text-muted-foreground">{label}</span>
    </li>
  )
}
