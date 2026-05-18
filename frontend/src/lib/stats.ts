import type { ScoreResponse } from "@/types/score"

export interface StatItem {
  label: string
  value: string
  hint?: string
  testid: string
}

function ownershipLabel(score: number | null): string {
  if (score === null) return "Unverified"
  if (score >= 0.85) return "High"
  if (score >= 0.6) return "Medium"
  return "Low"
}

function cesLabel(pct: number | null): string {
  if (pct === null) return "—"
  return `${pct.toFixed(1)}%`
}

export function statsFor(result: ScoreResponse): StatItem[] {
  return [
    {
      label: "Score confidence",
      value: `${Math.round(result.score_confidence * 100)}%`,
      hint: result.weighting_mode.replace(/_/g, " "),
      testid: "stat-confidence",
    },
    {
      label: "Owner-occupied",
      value: ownershipLabel(result.dimensions.ownership.value),
      hint: result.dimensions.ownership.note ?? undefined,
      testid: "stat-ownership",
    },
    {
      label: "DAC eligibility",
      value: result.is_dac === null ? "—" : result.is_dac ? "Yes" : "No",
      hint: result.is_dac ? "SB-535 disadvantaged community" : undefined,
      testid: "stat-dac",
    },
    {
      label: "CES percentile",
      value: cesLabel(result.ces_percentile ?? null),
      hint: "Higher = more burdened",
      testid: "stat-ces",
    },
  ]
}
