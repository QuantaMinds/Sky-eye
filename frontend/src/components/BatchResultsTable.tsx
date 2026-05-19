import { Link } from "react-router-dom"
import { formatAIN, formatScorePercent, scoreTier } from "@/lib/format"
import type { BatchResultRow } from "@/types/batch"

interface Props {
  results: BatchResultRow[]
}

/**
 * Top of the priority ranking. Shows ONLY scored rows — multi_unit_skipped
 * and api_failure are surfaced in BatchReasonsBreakdown above. This honors
 * the bulk-vs-detail rule: numbers only, no narratives. Each APN link
 * navigates to /score/:apn for the full per-lead view.
 *
 * Sort order: priority_score desc, stable for ties. Rows without a
 * priority_score (defensive — should never appear here) fall to the end.
 */
export function BatchResultsTable({ results }: Props) {
  const scored = results
    .filter((r) => r.scored_status === "scored" && r.priority_score != null)
    .sort((a, b) => (b.priority_score ?? -1) - (a.priority_score ?? -1))

  if (scored.length === 0) {
    return (
      <p data-testid="batch-results-empty" className="text-sm text-muted-foreground">
        No rows scored. Check the Excluded / Failed breakdown above.
      </p>
    )
  }

  return (
    <table data-testid="batch-results-table" className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
          <th className="py-2 pr-2">Score</th>
          <th className="py-2 pr-2">AIN</th>
          <th className="py-2 pr-2">Address</th>
          <th className="py-2 pr-2">Stream</th>
        </tr>
      </thead>
      <tbody>
        {scored.map((r) => (
          <tr key={`${r.result_index}-${r.resolved_ain}`} data-testid="batch-row"
              className="border-t border-border/60">
            <td className="py-2 pr-2 font-semibold tabular-nums"
                data-tier={scoreTier(r.priority_score ?? null) ?? "unknown"}>
              {formatScorePercent(r.priority_score ?? null)}
            </td>
            <td className="py-2 pr-2 font-mono text-xs">
              {r.resolved_ain ? (
                <Link to={`/score/${r.resolved_ain}`} className="underline">
                  {formatAIN(r.resolved_ain)}
                </Link>
              ) : "—"}
            </td>
            <td className="py-2 pr-2">{r.input_address}</td>
            <td className="py-2 pr-2 text-muted-foreground">{r.stream ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
