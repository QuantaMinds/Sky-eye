import { Card, CardContent } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { VerifyLink } from "@/components/VerifyLink"
import { formatScorePercent, scoreTier } from "@/lib/format"
import { DIMENSION_META } from "@/lib/dimension-meta"
import { cn } from "@/lib/utils"
import type { DimensionName, DimensionValue } from "@/types/score"

interface Props {
  name: DimensionName
  dim: DimensionValue
  verifyHref?: string
  verifyLabel?: string
}

const TIER_BAR = {
  high: "[&>[data-slot=progress-indicator]]:bg-emerald-500",
  medium: "[&>[data-slot=progress-indicator]]:bg-amber-500",
  low: "[&>[data-slot=progress-indicator]]:bg-rose-500",
} as const

export function DimensionCard({ name, dim, verifyHref, verifyLabel }: Props) {
  const meta = DIMENSION_META[name]
  const tier = scoreTier(dim.value)
  const pct = dim.value === null ? 0 : Math.round(dim.value * 100)

  return (
    <Card data-testid={`dimension-${name}`} data-tier={tier ?? "unknown"} className="py-4">
      <CardContent className="px-4 space-y-2">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="text-sm font-semibold">{meta.label}</h3>
          <span className="text-2xl font-bold tabular-nums">{formatScorePercent(dim.value)}</span>
        </div>
        <Progress value={pct} className={cn("h-2", tier ? TIER_BAR[tier] : undefined)} />
        {dim.note && <p className="text-sm text-muted-foreground">{dim.note}</p>}
        <div className="flex items-center justify-between pt-1">
          <span className="text-xs text-muted-foreground">Source: {dim.source}</span>
          {verifyHref && (
            <VerifyLink href={verifyHref} label={verifyLabel ?? "Verify"} />
          )}
        </div>
      </CardContent>
    </Card>
  )
}
