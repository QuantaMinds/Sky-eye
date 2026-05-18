import { Card, CardContent } from "@/components/ui/card"
import { DIMENSION_META } from "@/lib/dimension-meta"
import type { DimensionName } from "@/types/score"

interface Props {
  name: DimensionName
}

export function GhostDimensionCard({ name }: Props) {
  const meta = DIMENSION_META[name]
  return (
    <Card
      data-testid={`dimension-${name}`}
      data-tier="ghost"
      className="py-4 border-dashed bg-muted/30"
      aria-disabled="true"
    >
      <CardContent className="px-4 space-y-2 opacity-70">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="text-sm font-semibold text-muted-foreground">{meta.label}</h3>
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Phase 2 — coming soon
          </span>
        </div>
        <p className="text-sm text-muted-foreground">{meta.description}</p>
      </CardContent>
    </Card>
  )
}
