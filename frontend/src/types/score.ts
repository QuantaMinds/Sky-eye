export type DimensionName =
  | "roof_potential"
  | "income_qualification"
  | "ownership"
  | "bill_pain"
  | "equity_proxy"
  | "no_existing_solar"
  | "intent_signal"

export interface DimensionValue {
  value: number | null
  source: string
  note?: string | null
}

export type ScoreDimensions = Record<DimensionName, DimensionValue>

export type Stream = "private" | "dac_sash" | "not_residential"

export interface ScoreResponse {
  address: string
  lat: number
  lng: number
  score: number
  score_confidence: number
  weighting_mode: "all_signals_available" | "available_signals_only" | "no_signals"
  stream: Stream | null
  is_dac: boolean | null
  ces_percentile: number | null
  dimensions: ScoreDimensions
  narrative: string
  data_sources: string[]
  cached: Record<string, boolean>
  latency_ms: number
  apn?: string
  block_group_geoid?: string | null
  scored_at?: string
  is_demo?: boolean
}

export interface ScoreErrorResponse {
  error: string
  message?: string
}
