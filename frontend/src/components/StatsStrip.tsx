import { StatCard } from "@/components/StatCard"
import { statsFor } from "@/lib/stats"
import type { ScoreResponse } from "@/types/score"

interface Props {
  result: ScoreResponse
}

export function StatsStrip({ result }: Props) {
  const stats = statsFor(result)
  return (
    <section
      data-testid="stats-strip"
      className="grid grid-cols-2 gap-3 px-4 py-6 md:grid-cols-4 md:px-8"
      aria-label="Headline stats"
    >
      {stats.map((s) => (
        <StatCard key={s.testid} label={s.label} value={s.value} hint={s.hint} testid={s.testid} />
      ))}
    </section>
  )
}
