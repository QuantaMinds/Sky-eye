import { DimensionCard } from "@/components/DimensionCard"
import { GhostDimensionCard } from "@/components/GhostDimensionCard"
import { ACTIVE_DIMENSIONS, GHOST_DIMENSIONS } from "@/lib/dimension-meta"
import { verifyTargetFor } from "@/lib/dimension-verify"
import type { ScoreResponse } from "@/types/score"

interface Props {
  result: ScoreResponse
}

export function DimensionGrid({ result }: Props) {
  return (
    <section
      data-testid="dimension-grid"
      aria-label="Dimension breakdown"
      className="grid grid-cols-1 gap-3 px-4 py-6 md:grid-cols-2 md:px-8"
    >
      {ACTIVE_DIMENSIONS.map((name) => {
        const target = verifyTargetFor(name, result)
        return (
          <DimensionCard
            key={name}
            name={name}
            dim={result.dimensions[name]}
            verifyHref={target?.href}
            verifyLabel={target?.label}
          />
        )
      })}
      {GHOST_DIMENSIONS.map((name) => (
        <GhostDimensionCard key={name} name={name} />
      ))}
    </section>
  )
}
