/**
 * TS mirror of api/models/batch.py.
 * Mirrors api/services/_batch_scorer column-prefix shape too — fields are
 * optional because the scored, multi_unit_skipped, and api_failure rows
 * each carry a different subset.
 */

export type ScoredStatus = "scored" | "multi_unit_skipped" | "api_failure" | string

export interface BatchSubmitRequest {
  addresses: string[]
  installer_id?: string | null
}

export interface BatchAcceptResponse {
  job_id: string
  status: "queued"
  address_count: number
}

export interface BatchResultRow {
  job_id: string
  result_index: number
  input_address: string
  scored_at?: string | null
  scored_status: ScoredStatus

  // Scored rows
  geocoded_lat?: number | null
  geocoded_lng?: number | null
  priority_score?: number | null
  stream?: string | null
  resolved_ain?: string | null
  resolution_confidence?: string | null
  roof_potential?: number | null
  income_qualified?: number | null
  ownership?: number | null
  bill_pain?: number | null
  equity_strength?: number | null
  has_homeowners_exemption?: boolean | null
  total_value?: number | null
  sqft_main?: number | null
  year_built?: number | null

  // multi_unit_skipped / api_failure rows
  error_message?: string | null
}

export interface BatchStatusResponse {
  job_id: string
  status: "queued" | "processing" | "complete" | "unknown"
  address_count: number
  completed_count: number
  skipped_count: number
  failed_count: number
  skip_reasons?: Record<string, number> | null
  failure_reasons?: Record<string, number> | null
  results: BatchResultRow[]
}
