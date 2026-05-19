-- ============================================================================
-- TaxLens (Phase 5) — additive DDL
-- ============================================================================
-- The base TaxLens tables are already declared in api/infra/bigquery_schema.sql:
--
--   parcels_raw.permits        -- permits ingest target (LB scraper writes here)
--   leadlens.change_events     -- per-detection audit log
--
-- This file adds the one table the base schema did NOT reserve:
--
--   leadlens.taxlens_labels    -- hand-labeled ground truth, mirror of
--                                 fixtures/known_changes/labels.csv
--
-- Why a separate file: the base schema is a snapshot of what already exists in
-- prod. Adding the labels table additively keeps Phase 5's footprint reviewable
-- in isolation and lets us re-run this DDL without touching the base.
--
-- Naming choice: leadlens.taxlens_* (not a new dataset) — the labels table is
-- application-tier data that follows the leadlens lifecycle (retention,
-- partition policy, IAM), not raw upstream ingest.
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Hand-labeled ground truth for the change-detection precision benchmark.
--
-- Source of truth at file-level: fixtures/known_changes/labels.csv (built by
-- scripts/label_parcels.py). This BQ table mirrors that CSV so the benchmark
-- can also be re-run from BigQuery (e.g. a scheduled accuracy regression).
--
-- Mirror direction: CSV is canonical. A one-way loader copies CSV -> BQ. We do
-- NOT write back to CSV from BQ; the human label step always passes through
-- the CLI, and the CSV is the auditable trail.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.leadlens.taxlens_labels` (
  apn                              STRING NOT NULL,
  year_a                           INT64 NOT NULL,
  year_b                           INT64 NOT NULL,

  -- Ground-truth verdict (the y/n the labeler answered)
  has_change                       BOOL NOT NULL,

  -- One of: 'new_adu' | 'addition' | 'pool' | 'garage_conv' | 'demolition' | 'no_change'
  change_type                      STRING NOT NULL,
  notes                            STRING,

  -- Provenance for the imagery the labeler actually saw, so a future re-label
  -- can detect "the NAIP composite changed under us" drift.
  naip_a_date                      DATE,
  naip_b_date                      DATE,

  labeled_by                       STRING,                    -- email or initials; NULL for anonymous
  labeled_at                       TIMESTAMP NOT NULL,

  -- Composite primary key (BQ has no enforced PK; document the invariant)
  -- UNIQUE: (apn, year_a, year_b)
)
CLUSTER BY apn, has_change
OPTIONS (
  description = "Hand-labeled ground truth for TaxLens change detection benchmark. Mirror of fixtures/known_changes/labels.csv. Each row = one human-labeled (apn, year_a, year_b) triple. CSV is canonical; this table is the BQ mirror for scheduled accuracy regressions."
);
