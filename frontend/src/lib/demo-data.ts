import type { ScoreResponse } from "@/types/score"

const GHOST = { value: null, source: "demo", note: "Phase 2 — coming soon" }

const _DATA_SOURCES = [
  "Google Maps Platform Geocoding API",
  "Google Maps Platform Solar API",
  "US Census ACS 5-year (2024 vintage)",
  "NREL PVWatts V8",
  "LA County Assessor (Rolls 2021-2024, BigQuery)",
  "CPUC Electric IOU Territory + LA County DRP city boundaries (utility)",
  "OEHHA SB-535 Disadvantaged Communities (Tribal update 2023/2024)",
  "Google Vertex AI (Gemini 2.5 Flash)",
]

const DEMO_BELMONT: ScoreResponse = {
  apn: "9999001001",
  address: "DEMO — Belmont Shore SFR, Long Beach, CA 90803",
  lat: 33.7625,
  lng: -118.1551,
  score: 0.83,
  score_confidence: 0.71,
  weighting_mode: "available_signals_only",
  stream: "private",
  is_dac: false,
  ces_percentile: 22.1,
  block_group_geoid: "060375759001",
  dimensions: {
    roof_potential: { value: 0.88, source: "demo", note: "1,130 sqft south-facing, low shading" },
    income_qualification: { value: 0.72, source: "demo", note: "Block-group MHI ~$118k (above LA median)" },
    ownership: { value: 0.95, source: "demo", note: "Homeowner's Exemption on file" },
    bill_pain: { value: 0.81, source: "demo", note: "LADWP residential blended ~$0.31/kWh" },
    equity_proxy: { value: 0.79, source: "demo", note: "Tenure 18 years, base-year 2006" },
    no_existing_solar: GHOST,
    intent_signal: GHOST,
  },
  narrative:
    "Single-family home in Belmont Shore with a strong south-facing roof segment and an active Homeowner's Exemption. The LADWP service territory retains 1:1 net metering, so payback estimates are unusually favorable for the area.",
  data_sources: _DATA_SOURCES,
  cached: {},
  latency_ms: 0,
  scored_at: "2026-05-18T15:00:00Z",
  is_demo: true,
}

const DEMO_BIXBY: ScoreResponse = {
  apn: "9999001002",
  address: "DEMO — Bixby Knolls SFR, Long Beach, CA 90807",
  lat: 33.838,
  lng: -118.183,
  score: 0.77,
  score_confidence: 0.71,
  weighting_mode: "available_signals_only",
  stream: "private",
  is_dac: false,
  ces_percentile: 38.4,
  block_group_geoid: "060375721001",
  dimensions: {
    roof_potential: { value: 0.74, source: "demo", note: "Partial east/west pitch, moderate shading" },
    income_qualification: { value: 0.68, source: "demo", note: "Block-group MHI ~$95k" },
    ownership: { value: 0.62, source: "demo", note: "No HX on file (inherited or in trust)" },
    bill_pain: { value: 0.76, source: "demo", note: "LADWP residential blended ~$0.31/kWh" },
    equity_proxy: { value: 0.98, source: "demo", note: "Tenure 51 years (base-year 1975)" },
    no_existing_solar: GHOST,
    intent_signal: GHOST,
  },
  narrative:
    "Long-tenured home owned since 1975. The 51-year tenure suggests strong equity and likely long-term owner-occupancy, though the Homeowner's Exemption is not on file (could be inherited or in trust). LADWP 1:1 net metering retained.",
  data_sources: _DATA_SOURCES,
  cached: {},
  latency_ms: 0,
  scored_at: "2026-05-18T15:00:00Z",
  is_demo: true,
}

const DEMO_BOYLE: ScoreResponse = {
  apn: "9999001003",
  address: "DEMO — Boyle Heights SFR, Los Angeles, CA 90033",
  lat: 34.0312,
  lng: -118.2103,
  score: 0.71,
  score_confidence: 0.71,
  weighting_mode: "available_signals_only",
  stream: "dac_sash",
  is_dac: true,
  ces_percentile: 87.9,
  block_group_geoid: "060372046001",
  dimensions: {
    roof_potential: { value: 0.69, source: "demo", note: "Modest south exposure, mature tree shading" },
    income_qualification: { value: 0.94, source: "demo", note: "Block-group MHI ~$42k — DAC eligible" },
    ownership: { value: 0.88, source: "demo", note: "Homeowner's Exemption on file" },
    bill_pain: { value: 0.55, source: "demo", note: "LADWP residential blended ~$0.31/kWh" },
    equity_proxy: { value: 0.62, source: "demo", note: "Tenure 22 years, base-year 2003" },
    no_existing_solar: GHOST,
    intent_signal: GHOST,
  },
  narrative:
    "Owner-occupied home in an SB-535 disadvantaged community tract — eligible for the DAC-SASH no-cost installation program through GRID Alternatives. Income qualification is strong; bill-pain is moderate under LADWP.",
  data_sources: _DATA_SOURCES,
  cached: {},
  latency_ms: 0,
  scored_at: "2026-05-18T15:00:00Z",
  is_demo: true,
}

export const DEMO_SCORES: ScoreResponse[] = [DEMO_BELMONT, DEMO_BIXBY, DEMO_BOYLE]

export function lookupDemoByApn(apn: string): ScoreResponse | null {
  const target = apn.replace(/\D/g, "")
  return DEMO_SCORES.find((s) => s.apn === target) ?? null
}
