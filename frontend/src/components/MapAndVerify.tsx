import { MapVerifyPanel } from "@/components/MapVerifyPanel"
import { StaticMap } from "@/components/StaticMap"
import type { ScoreResponse } from "@/types/score"

interface Props {
  result: ScoreResponse
}

export function MapAndVerify({ result }: Props) {
  return (
    <section
      data-testid="map-and-verify"
      aria-label="Map and verification"
      className="grid grid-cols-1 gap-4 px-4 py-4 md:grid-cols-2 md:px-8"
    >
      <StaticMap lat={result.lat} lng={result.lng} alt={`Satellite view of ${result.address}`} />
      <MapVerifyPanel result={result} />
    </section>
  )
}
