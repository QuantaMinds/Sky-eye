import { useState } from "react"
import { Link } from "react-router-dom"
import { formatScorePercent, scoreTier } from "@/lib/format"
import type { BatchResultRow } from "@/types/batch"
import { VerifyLink } from "./VerifyLink"

interface Props {
  results: BatchResultRow[]
}

type Tier = "top" | "strong" | "workable" | "skip"

function getTier(score: number): Tier {
  if (score > 0.80) return "top"
  if (score >= 0.65) return "strong"
  if (score >= 0.50) return "workable"
  return "skip"
}

export function BatchResultsTable({ results }: Props) {
  const [activeTier, setActiveTier] = useState<Tier | null>(null)

  const scored = results
    .filter((r) => r.scored_status === "scored" && r.priority_score != null)
    .sort((a, b) => (b.priority_score ?? -1) - (a.priority_score ?? -1))

  const topTier = scored.filter(r => getTier(r.priority_score!) === "top")
  const strongTier = scored.filter(r => getTier(r.priority_score!) === "strong")
  const workableTier = scored.filter(r => getTier(r.priority_score!) === "workable")
  const skipTier = scored.filter(r => getTier(r.priority_score!) === "skip")

  if (scored.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card p-8 text-center text-sm text-muted-foreground shadow-sm">
        No rows scored. Check the Excluded / Failed breakdown above.
      </div>
    )
  }

  const activeRows = activeTier === "top" ? topTier
    : activeTier === "strong" ? strongTier
    : activeTier === "workable" ? workableTier
    : []

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Tier Dashboard View */}
      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
        {[
          { id: "top", label: "Top tier (> 0.80)", count: topTier.length, color: "bg-emerald-500", items: topTier },
          { id: "strong", label: "Strong (0.65 - 0.80)", count: strongTier.length, color: "bg-blue-500", items: strongTier },
          { id: "workable", label: "Workable (0.50 - 0.65)", count: workableTier.length, color: "bg-amber-500", items: workableTier },
          { id: "skip", label: "Skip (< 0.50)", count: skipTier.length, color: "bg-muted-foreground", items: skipTier, hidden: true },
        ].map(t => (
          <div key={t.id} className={`flex flex-col rounded-xl border border-border bg-card p-5 shadow-sm transition-all ${activeTier === t.id ? 'ring-2 ring-primary' : 'hover:border-primary/30'}`}>
            <div className="flex items-center gap-2 mb-2">
              <div className={`h-2.5 w-2.5 rounded-full ${t.color}`} />
              <h3 className="text-sm font-semibold text-foreground">{t.label}</h3>
            </div>
            <div className="flex items-center justify-between mt-auto pt-2">
              <span className="text-2xl font-bold tracking-tight">{t.count} <span className="text-sm font-normal text-muted-foreground">leads</span></span>
              {!t.hidden ? (
                <button
                  onClick={() => setActiveTier(activeTier === t.id ? null : t.id as Tier)}
                  className="text-xs font-semibold text-primary hover:underline uppercase tracking-wider"
                >
                  {activeTier === t.id ? 'Hide' : 'Show me'}
                </button>
              ) : (
                <span className="text-xs text-muted-foreground/50 uppercase tracking-wider">[hidden]</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Active Tier Table View */}
      {activeTier && (
        <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden animate-in slide-in-from-top-4 fade-in duration-300">
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="bg-muted/30 text-muted-foreground border-b border-border">
                <tr>
                  <th className="px-6 py-4 font-semibold uppercase tracking-wider text-xs">Address</th>
                  <th className="px-6 py-4 font-semibold uppercase tracking-wider text-xs">Score</th>
                  <th className="px-6 py-4 font-semibold uppercase tracking-wider text-xs">Years owned</th>
                  <th className="px-6 py-4 font-semibold uppercase tracking-wider text-xs">Roof</th>
                  <th className="px-6 py-4 font-semibold uppercase tracking-wider text-xs">Income</th>
                  <th className="px-6 py-4 font-semibold uppercase tracking-wider text-xs text-right">Verify</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {activeRows.map((r) => {
                  const currentYear = new Date().getFullYear()
                  const yearsOwned = r.year_built ? currentYear - r.year_built : "—"
                  
                  return (
                    <tr key={`${r.result_index}-${r.resolved_ain}`} className="group transition-colors hover:bg-muted/30">
                      <td className="px-6 py-4">
                        <Link to={`/score/${r.resolved_ain}`} className="font-medium text-foreground group-hover:text-primary transition-colors">
                          {r.input_address}
                        </Link>
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex items-center rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
                          {formatScorePercent(r.priority_score ?? null)}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-muted-foreground">{yearsOwned}</td>
                      <td className="px-6 py-4 text-muted-foreground">{r.roof_potential ? formatScorePercent(r.roof_potential) : "—"}</td>
                      <td className="px-6 py-4 text-muted-foreground">{r.income_qualified ? formatScorePercent(r.income_qualified) : "—"}</td>
                      <td className="px-6 py-4 text-right">
                        <VerifyLink
                          href={`https://portal.assessor.lacounty.gov/parceldetail/${r.resolved_ain}`}
                          label="LA Assessor ↗"
                          className="text-xs font-semibold text-primary hover:underline"
                        />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
