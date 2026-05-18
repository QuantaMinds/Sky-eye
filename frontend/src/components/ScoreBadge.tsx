import { cn } from "@/lib/utils"
import { formatScorePercent, scoreTier } from "@/lib/format"

interface Props {
  score: number | null
  size?: "sm" | "lg"
}

const TIER_CLASS = {
  high: "bg-emerald-100 text-emerald-900 ring-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-100",
  medium: "bg-amber-100 text-amber-900 ring-amber-300 dark:bg-amber-900/40 dark:text-amber-100",
  low: "bg-rose-100 text-rose-900 ring-rose-300 dark:bg-rose-900/40 dark:text-rose-100",
} as const

export function ScoreBadge({ score, size = "lg" }: Props) {
  const tier = scoreTier(score)
  const percent = formatScorePercent(score)
  const isUnknown = tier === null

  return (
    <div
      role="status"
      aria-label={isUnknown ? "Score unavailable" : `Score ${percent} of 100`}
      data-testid="score-badge"
      data-tier={tier ?? "unknown"}
      className={cn(
        "inline-flex items-baseline gap-1 rounded-xl ring-1 px-3 py-1.5 font-semibold tabular-nums",
        size === "lg" ? "text-4xl" : "text-xl",
        isUnknown
          ? "bg-muted text-muted-foreground ring-border"
          : TIER_CLASS[tier],
      )}
    >
      <span>{percent}</span>
      {!isUnknown && (
        <span className={cn("font-medium opacity-70", size === "lg" ? "text-base" : "text-xs")}>/100</span>
      )}
    </div>
  )
}
