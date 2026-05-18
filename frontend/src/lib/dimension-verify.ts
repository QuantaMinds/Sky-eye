import {
  assessorPortalUrl,
  censusAcsBlockGroupUrl,
  projectSunroofUrl,
  utilityRateSheetUrl,
} from "@/lib/verify-urls"
import type { DimensionName, ScoreResponse } from "@/types/score"

export interface VerifyTarget {
  href: string
  label: string
}

export function verifyTargetFor(
  name: DimensionName,
  result: ScoreResponse,
): VerifyTarget | null {
  switch (name) {
    case "roof_potential":
      return { href: projectSunroofUrl(result.lat, result.lng), label: "Project Sunroof" }
    case "income_qualification":
      return {
        href: censusAcsBlockGroupUrl(result.block_group_geoid),
        label: "Census ACS",
      }
    case "ownership":
      return result.apn
        ? { href: assessorPortalUrl(result.apn), label: "LA Assessor" }
        : null
    case "bill_pain": {
      const utility = inferUtility(result.dimensions.bill_pain.note ?? null)
      return { href: utilityRateSheetUrl(utility), label: "Utility rate sheet" }
    }
    case "equity_proxy":
      return result.apn
        ? { href: assessorPortalUrl(result.apn), label: "LA Assessor" }
        : null
    case "no_existing_solar":
    case "intent_signal":
      return null
  }
}

function inferUtility(note: string | null): string | null {
  if (!note) return null
  if (/LADWP/i.test(note)) return "LADWP"
  if (/SCE/i.test(note)) return "SCE"
  return null
}
