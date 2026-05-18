export type ScoreTier = "low" | "medium" | "high"

export function formatAIN(apn: string): string {
  const digits = apn.replace(/\D/g, "")
  if (digits.length !== 10) return apn
  return `${digits.slice(0, 4)}-${digits.slice(4, 7)}-${digits.slice(7, 10)}`
}

export function unformatAIN(apn: string): string {
  return apn.replace(/\D/g, "")
}

export function formatScorePercent(score: number | null): string {
  if (score === null || Number.isNaN(score)) return "—"
  return `${Math.round(score * 100)}`
}

export function scoreTier(score: number | null): ScoreTier | null {
  if (score === null || Number.isNaN(score)) return null
  if (score >= 0.8) return "high"
  if (score >= 0.6) return "medium"
  return "low"
}

export function formatTenureYears(yearsOwned: number | null): string {
  if (yearsOwned === null || yearsOwned < 0) return "—"
  return `${Math.round(yearsOwned)} years`
}

export function formatUsd(amount: number | null, options?: { round?: number }): string {
  if (amount === null || Number.isNaN(amount)) return "—"
  const round = options?.round ?? 1
  const rounded = Math.round(amount / round) * round
  return `$${rounded.toLocaleString("en-US")}`
}

export function formatKw(kw: number | null): string {
  if (kw === null || Number.isNaN(kw)) return "—"
  return `${kw.toFixed(1)} kW`
}
