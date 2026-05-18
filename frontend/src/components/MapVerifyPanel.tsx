import { VerifyLink } from "@/components/VerifyLink"
import {
  assessorPortalUrl,
  censusAcsBlockGroupUrl,
  googleSatelliteUrl,
  projectSunroofUrl,
} from "@/lib/verify-urls"
import type { ScoreResponse } from "@/types/score"

interface Props {
  result: ScoreResponse
}

export function MapVerifyPanel({ result }: Props) {
  const { lat, lng, apn, block_group_geoid } = result
  return (
    <section
      data-testid="map-verify-panel"
      aria-label="Verification links"
      className="flex flex-col gap-2"
    >
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Verify against the source
      </p>
      <VerifyLink variant="button" href={googleSatelliteUrl(lat, lng)} label="Google Maps (satellite)" />
      {apn && (
        <VerifyLink variant="button" href={assessorPortalUrl(apn)} label="LA County Assessor Portal" />
      )}
      <VerifyLink variant="button" href={projectSunroofUrl(lat, lng)} label="Google Project Sunroof" />
      <VerifyLink
        variant="button"
        href={censusAcsBlockGroupUrl(block_group_geoid)}
        label="Census ACS block group"
      />
    </section>
  )
}
