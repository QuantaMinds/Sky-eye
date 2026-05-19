import { useMemo } from "react"
import { useParams } from "react-router-dom"
import { AddressHeader } from "@/components/AddressHeader"
import { DimensionGrid } from "@/components/DimensionGrid"
import { MapAndVerify } from "@/components/MapAndVerify"
import { NarrativeSection } from "@/components/NarrativeSection"
import { PageFooter } from "@/components/PageFooter"
import { StatsStrip } from "@/components/StatsStrip"
import { loadScore } from "@/lib/session-store"
import { ScoreNotFound } from "@/pages/ScoreNotFound"
import type { ScoreResponse } from "@/types/score"

function resolveResult(apn: string | undefined): ScoreResponse | null {
  if (!apn) return null
  return loadScore(apn) || null
}

export function ScoreResult() {
  const { apn } = useParams<{ apn: string }>()
  const result = useMemo(() => resolveResult(apn), [apn])

  if (!result) return <ScoreNotFound apn={apn} />

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AddressHeader result={result} />
      <StatsStrip result={result} />
      <MapAndVerify result={result} />
      <DimensionGrid result={result} />
      <NarrativeSection narrative={result.narrative} scoreConfidence={result.score_confidence} />
      <PageFooter
        dataSources={result.data_sources}
        scoredAt={result.scored_at}
        latencyMs={result.latency_ms}
      />
    </div>
  )
}
