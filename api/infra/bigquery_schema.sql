-- ============================================================================
-- LeadLens BigQuery Schema DDL
-- ============================================================================
-- Project:  sky-eye-496604
-- Region:   us-west1
-- Datasets: parcels_raw  -- raw ingested data, append-only, never mutated
--           parcels      -- unified production view, what application reads
--           leadlens     -- application data (job state, scored results, audit)
--
-- Naming conventions:
--   - snake_case for everything
--   - GEOGRAPHY type for all spatial columns, EPSG:4326 (WGS84)
--   - Clustering on GEOGRAPHY columns uses S2 cell hierarchies natively
--   - All STRING columns from upstream raw CSVs preserved as-is in *_raw
--   - Normalization happens in parcels.la_county view layer
--
-- Truth-first principle: every scored result includes provenance and
-- confidence_level on dimensions where source data is approximate.
-- ============================================================================


-- ============================================================================
-- DATASET CREATION
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS `sky-eye-496604.parcels_raw`
OPTIONS (
  location = "us-west1",
  description = "Raw ingested data from LA County Assessor and other authoritative sources. Append-only, immutable per ingest run."
);

CREATE SCHEMA IF NOT EXISTS `sky-eye-496604.parcels`
OPTIONS (
  location = "us-west1",
  description = "Unified production parcel data, normalized schema, what the API reads."
);

CREATE SCHEMA IF NOT EXISTS `sky-eye-496604.leadlens`
OPTIONS (
  location = "us-west1",
  description = "Application data: scored results, batch jobs, audit trail."
);


-- ============================================================================
-- parcels_raw — Raw ingested upstream data
-- ============================================================================

-- ----------------------------------------------------------------------------
-- LA County Assessor attribute data
-- Source: data.lacounty.gov "Rolls 2021-Present" CSV bulk download
-- Volume: ~9.7M rows (one per parcel per roll year, 2021-2024)
-- Update frequency: annual, July
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.parcels_raw.la_county_attributes` (
  -- All STRING preserved from source CSV; type coercion happens in parcels.la_county
  ain                              STRING NOT NULL,
  roll_year                        STRING NOT NULL,

  -- Use classification
  use_code                         STRING,                    -- e.g. '0100' for SFR
  use_code_1st_digit               STRING,                    -- 'Residential' / 'Commercial' / etc
  use_code_2nd_digit               STRING,                    -- 'Single Family Residence' / etc
  property_use_code                STRING,                    -- same as use_code typically

  -- Building characteristics
  year_built                       STRING,
  effective_year                   STRING,
  square_footage                   STRING,
  number_of_bedrooms               STRING,
  number_of_bathrooms              STRING,
  number_of_units                  STRING,

  -- Address
  property_location                STRING,                    -- Full situs address as published
  city                             STRING,
  zip_code                         STRING,                    -- 5+4 format
  zip_code_5                       STRING,                    -- 5-digit only

  -- Geographic
  location_latitude                STRING,                    -- WGS84 centroid
  location_longitude               STRING,                    -- WGS84 centroid

  -- Prop 13 base years (CRITICAL for tenure calculation)
  land_base_year                   STRING,                    -- '0' = sentinel for null
  improvement_base_year            STRING,                    -- '0' = sentinel for null
  recording_date                   STRING,                    -- '3/21/1997 8:00:00 AM' format

  -- Valuation
  land_value                       STRING,
  improvement_value                STRING,
  total_value_land_improvement     STRING,                    -- col 25, use this for residential
  total_value                      STRING,                    -- col 33, includes personal property

  -- Exemption signals
  home_owners_exemption            STRING,                    -- '7000' or '0' (legitimate zero, NOT a sentinel)
  real_estate_exemption            STRING,
  total_exemption                  STRING,
  property_taxable                 STRING,                    -- 'Y' or 'N'

  -- Ingest provenance
  source_url                       STRING NOT NULL,
  ingested_at                      TIMESTAMP NOT NULL,
  ingest_batch_id                  STRING NOT NULL            -- UUID for the ingest run
)
PARTITION BY DATE(ingested_at)
CLUSTER BY ain, roll_year
OPTIONS (
  description = "Raw LA County Assessor roll data. All fields STRING; normalization in parcels.la_county. Note: home_owners_exemption='0' is legitimate (no exemption filed), not a null sentinel. land_base_year='0' and improvement_base_year='0' ARE sentinels requiring NULLIF guards downstream."
);


-- ----------------------------------------------------------------------------
-- LA County parcel geometries
-- Source: data.lacounty.gov LA County Parcels shapefile (~322MB compressed)
-- Volume: ~2.4M polygon geometries
-- Update frequency: monthly
-- Reprojected from EPSG:2229 (CA State Plane V) to EPSG:4326 (WGS84) at ingest
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.parcels_raw.la_county_geometries` (
  ain                              STRING NOT NULL,           -- Primary key for join to attributes

  -- Spatial
  geom                             GEOGRAPHY NOT NULL,        -- Polygon in WGS84
  center_lat                       FLOAT64,                   -- Pre-baked centroid (WGS84)
  center_lon                       FLOAT64,                   -- Pre-baked centroid (WGS84)
  shape_area_sqft                  FLOAT64,                   -- Original from shapefile
  shape_length_ft                  FLOAT64,

  -- Minimal attribute subset present in shapefile DBF
  situs_house                      STRING,
  situs_street                     STRING,
  situs_full_address               STRING,
  situs_city                       STRING,
  situs_zip                        STRING,
  use_code_from_shapefile          STRING,                    -- May differ from attributes CSV; investigate if delta >0.5%
  year_built_from_shapefile        STRING,
  sqft_main_from_shapefile         STRING,

  -- Ingest provenance
  source_url                       STRING NOT NULL,
  source_crs                       STRING NOT NULL,           -- 'EPSG:2229' for verification
  ingested_at                      TIMESTAMP NOT NULL,
  ingest_batch_id                  STRING NOT NULL
)
CLUSTER BY geom, ain
OPTIONS (
  description = "Reprojected LA County parcel polygons. CLUSTER BY geom uses S2 cells for native spatial pruning. Always pair coordinate queries with bbox pre-filter on center_lat/center_lon for sub-100ms latency."
);


-- ----------------------------------------------------------------------------
-- Use code dictionary (derived from raw attributes via SELECT DISTINCT)
-- Volume: ~200 distinct use codes
-- Update frequency: rebuild on each attributes ingest
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.parcels_raw.use_codes` (
  use_code                         STRING NOT NULL,           -- '0100', '0200', etc
  use_category                     STRING,                    -- 'Residential', 'Commercial', etc
  use_description                  STRING,                    -- 'Single Family Residence', etc
  is_residential                   BOOL NOT NULL,             -- Computed from use_category
  is_dac_sash_eligible_type        BOOL NOT NULL,             -- Residential AND SFR/duplex/triplex/condo
  derived_at                       TIMESTAMP NOT NULL,
  derived_from_roll_year           STRING NOT NULL
)
CLUSTER BY use_code
OPTIONS (
  description = "Use code lookup derived from SELECT DISTINCT on raw attributes. Rebuild on each attributes ingest to stay current with roll."
);


-- ----------------------------------------------------------------------------
-- Utility service territories
-- Sources: CPUC Electric IOU FeatureServer (SCE) + LA County DRP boundary (LADWP proxy)
-- Volume: ~10 rows
-- Update frequency: rarely (regulatory changes)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.parcels_raw.utility_territories` (
  utility_name                     STRING NOT NULL,           -- 'LADWP' | 'SCE' | 'BURBANK_WP' | etc
  geom                             GEOGRAPHY NOT NULL,
  source_url                       STRING NOT NULL,
  source_note                      STRING,                    -- e.g. 'LA City boundary used as LADWP proxy'
  ingested_at                      TIMESTAMP NOT NULL
)
CLUSTER BY geom
OPTIONS (
  description = "Utility service area polygons. LADWP uses LA City boundary as proxy (covers >99% of residential LADWP customers). Muni utilities Burbank/Glendale/Pasadena/Vernon/Azusa/Cerritos tracked as Phase 1.5d.2 backlog."
);


-- ----------------------------------------------------------------------------
-- Utility rate lookup (hand-maintained)
-- Volume: ~5 rows
-- Update frequency: annually (after each utility tariff filing)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.parcels_raw.utility_rates` (
  utility_name                     STRING NOT NULL,           -- Matches utility_territories.utility_name
  representative_rate              NUMERIC,                   -- $/kWh blended residential
  tariff_variant                   STRING,                    -- 'R-1A' | 'TOU-D-PRIME' | NULL for fallback
  nem_regime                       STRING,                    -- '1:1 retained' | 'NEM 3.0 (ACC export)' | NULL
  rate_source_note                 STRING,                    -- Provenance text for Gemini narrative hedging
  confidence_level                 STRING NOT NULL,           -- 'precise' | 'approximate' | 'fallback'
  effective_date                   DATE NOT NULL,
  source_url                       STRING NOT NULL,
  ingested_at                      TIMESTAMP NOT NULL
)
CLUSTER BY utility_name
OPTIONS (
  description = "Per-utility representative residential rates. confidence_level drives Gemini hedging: 'fallback' rows render as 'utility not yet identified for this address' in narrative."
);


-- ----------------------------------------------------------------------------
-- SB 535 Disadvantaged Communities (DAC) tract polygons
-- Source: OEHHA CalEnviroScreen 4.0 + Tribal 2023/2024 update
-- Volume: 1,173 LA County tracts (of ~2,500 total LA tracts; ~47%)
-- Update frequency: ~every 2-3 years per OEHHA release cycle
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.parcels_raw.dac_tracts` (
  tract_geoid                      STRING NOT NULL,           -- 11-digit Census tract GEOID
  zip                              STRING,
  population                       INT64,
  ces_score                        FLOAT64,                   -- CalEnviroScreen total score
  ces_percentile                   FLOAT64,                   -- 0-100, higher = more disadvantaged
  is_sb535_dac                     BOOL NOT NULL,
  is_tribal                        BOOL NOT NULL,
  geom                             GEOGRAPHY NOT NULL,
  source_url                       STRING NOT NULL,
  oehha_release_version            STRING NOT NULL,           -- 'CES 4.0 2022 + Tribal 2024'
  ingested_at                      TIMESTAMP NOT NULL
)
CLUSTER BY geom, tract_geoid
OPTIONS (
  description = "SB 535 DAC tracts. is_sb535_dac=TRUE OR is_tribal=TRUE means DAC-SASH eligible. 1,173 LA County tracts qualify."
);


-- ----------------------------------------------------------------------------
-- Census ACS median household income by block group (LA County only)
-- Source: US Census Bureau ACS 5-year 2020-2024
-- Volume: ~6,500 LA County block groups
-- Update frequency: annual (December release)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.parcels_raw.acs_income_bg` (
  geoid_bg                         STRING NOT NULL,           -- 12-digit block group GEOID
  state_fips                       STRING NOT NULL,           -- '06' for CA
  county_fips                      STRING NOT NULL,           -- '037' for LA County
  tract_geoid                      STRING NOT NULL,           -- 11-digit (parent tract)
  median_household_income          INT64,                     -- Dollars, NULL if MOE too wide
  median_household_income_moe      INT64,                     -- Margin of error
  total_households                 INT64,
  acs_release                      STRING NOT NULL,           -- 'ACS_5Y_2020_2024'
  source_url                       STRING NOT NULL,
  ingested_at                      TIMESTAMP NOT NULL
)
CLUSTER BY geoid_bg
OPTIONS (
  description = "Census ACS median household income per block group for LA County. Used for income_qualified dimension calibration."
);


-- ----------------------------------------------------------------------------
-- LA County permit database (for TaxLens — Phase 2)
-- Source: TBD (LA County BSD or city-by-city APIs)
-- Volume: depends on date window
-- Update frequency: TBD
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.parcels_raw.permits` (
  permit_id                        STRING NOT NULL,
  ain                              STRING,                    -- May be NULL if permit predates AIN-tagging
  permit_type                      STRING,                    -- 'Building' | 'ADU' | 'Pool' | 'Solar' | etc
  permit_status                    STRING,                    -- 'Issued' | 'Finaled' | 'Expired' | etc
  application_date                 DATE,
  issued_date                      DATE,
  finaled_date                     DATE,
  description                      STRING,
  estimated_value                  NUMERIC,
  city                             STRING,
  zip                              STRING,
  source_jurisdiction              STRING NOT NULL,           -- 'LB' | 'LA_CITY' | 'LA_COUNTY' | etc
  source_url                       STRING NOT NULL,
  ingested_at                      TIMESTAMP NOT NULL
)
PARTITION BY issued_date
CLUSTER BY ain, source_jurisdiction
OPTIONS (
  description = "Building permits keyed to AIN where possible. Used by TaxLens to cross-reference detected change events against legal permit history. Phase 2."
);


-- ----------------------------------------------------------------------------
-- OWNER MAIL MERGE (Phase 1.5c.2 — DEFERRED, awaiting PRA bulk dump)
-- Source: LA County Assessor Public Records Act request
-- Volume: ~2.4M rows (one per parcel)
-- Update frequency: annual
-- Status: schema reserved, table not yet populated
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.parcels_raw.owner_mail_merge` (
  ain                              STRING NOT NULL,
  owner_name_1                     STRING,                    -- Primary owner of record
  owner_name_2                     STRING,                    -- Co-owner if joint
  mail_address_full                STRING,                    -- Concatenated mailing address
  mail_address_street              STRING,
  mail_address_city                STRING,
  mail_address_state               STRING,
  mail_address_zip                 STRING,
  mail_address_country             STRING,

  -- Computed at ingest for downstream classifier
  mail_state_matches_ca            BOOL,
  mail_zip_matches_situs_zip       BOOL,                      -- Joined against parcels.la_county.zip

  source_url                       STRING NOT NULL,
  source_type                      STRING NOT NULL,           -- 'PRA_bulk' | 'commercial_vendor' | 'manual_enrichment'
  ingested_at                      TIMESTAMP NOT NULL,
  ingest_batch_id                  STRING NOT NULL
)
CLUSTER BY ain
OPTIONS (
  description = "Owner name and mailing address from LA County Assessor PRA bulk dump. POPULATING THIS TABLE ACTIVATES TIERS 2-7 OF THE OWNERSHIP CLASSIFIER (OUT_OF_STATE_LANDLORD, ABSENTEE_INVESTOR_POBOX, CORPORATE_INSTITUTIONAL, FAMILY_TRUST_POTENTIAL_OCCUPANT) with no code change required. Currently unpopulated; classifier runs in 3-bucket fallback mode."
);


-- ============================================================================
-- parcels — Unified production view
-- ============================================================================

-- ----------------------------------------------------------------------------
-- The main parcels table — what the API reads
-- Built by scripts/07_build_unified_parcels.sql
-- Joins: la_county_attributes (latest roll) + la_county_geometries + use_codes
-- Rebuild: full refresh on each attributes ingest
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.parcels.la_county` (
  -- Primary key
  ain                              STRING NOT NULL,

  -- Source roll year (latest available)
  roll_year                        STRING NOT NULL,

  -- Use classification (typed and normalized)
  use_code                         STRING,
  use_category                     STRING,                    -- From use_codes lookup, e.g. 'Residential'
  use_description                  STRING,                    -- e.g. 'Single Family Residence'
  is_residential                   BOOL NOT NULL,
  is_dac_sash_eligible_type        BOOL NOT NULL,

  -- Address (parsed and normalized)
  situs_street                     STRING,
  situs_unit                       STRING,
  situs_city                       STRING,
  situs_zip                        STRING,                    -- 5-digit
  situs_full_address               STRING,                    -- For display

  -- Spatial
  geom                             GEOGRAPHY,                 -- May be NULL if attributes row has no matching geometry (orphan, <0.5% expected)
  center_lat                       FLOAT64,
  center_lon                       FLOAT64,

  -- Building characteristics (typed)
  year_built                       INT64,                     -- NULL if source was '0'
  effective_year                   INT64,
  sqft_main                        INT64,                     -- NULL if source was '0'
  bedrooms                         INT64,
  bathrooms                        FLOAT64,                   -- May be e.g. 2.5
  units                            INT64,

  -- Tenure (Prop 13)
  -- arms_length_year = LEAST(NULLIF(land_base_year,'0'), NULLIF(improvement_base_year,'0'))
  arms_length_year                 INT64,                     -- The longer-held of the two base years
  recording_year                   INT64,                     -- May be more recent (trust transfer, etc) — NOT used for tenure

  -- Valuation (typed, with NULLIF guards on '0' sentinels)
  land_value                       NUMERIC,
  improvement_value                NUMERIC,
  total_value                      NUMERIC,                   -- From total_value_land_improvement (col 25)

  -- Exemption signals
  has_homeowners_exemption         BOOL NOT NULL,             -- TRUE if home_owners_exemption > 0
  homeowners_exemption_amount      NUMERIC,                   -- Typically $7,000 if active, 0 if not
  is_taxable                       BOOL NOT NULL,             -- TRUE if property_taxable = 'Y'

  -- Stream routing (computed)
  -- residential + (is_taxable=FALSE OR in_dac_tract) → 'dac_sash'
  -- residential + is_taxable=TRUE + NOT in_dac_tract → 'private'
  -- not residential → 'not_residential'
  stream                           STRING NOT NULL,

  -- Data freshness
  attributes_ingested_at           TIMESTAMP NOT NULL,
  geometry_ingested_at             TIMESTAMP NOT NULL,
  rebuilt_at                       TIMESTAMP NOT NULL
)
CLUSTER BY geom, is_residential, situs_zip
OPTIONS (
  description = "Unified parcel table — production read source. Built nightly from latest parcels_raw. CLUSTER BY geom enables S2-based spatial pruning; secondary cluster on is_residential supports the dominant filter; tertiary on zip supports ZIP-based batch queries."
);


-- ============================================================================
-- leadlens — Application data
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Batch scoring jobs (header table)
-- Volume: low (one row per batch request)
-- Retention: 90 days for free tier, configurable
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.leadlens.batch_jobs` (
  job_id                           STRING NOT NULL,           -- UUID
  installer_id                     STRING,                    -- For white-label branding; NULL for direct

  -- Request shape
  request_type                     STRING NOT NULL,           -- 'address_list' | 'zip_code' | 'single'
  request_input                    STRING,                    -- ZIP code or first 3 addresses snippet for human readability
  address_count                    INT64 NOT NULL,

  -- State
  status                           STRING NOT NULL,           -- 'queued' | 'processing' | 'complete' | 'failed' | 'expired'
  status_message                   STRING,                    -- Human-readable detail

  -- Progress
  -- completed_count: rows that scored end-to-end (scored_status='scored')
  -- skipped_count:   rows intentionally excluded by policy (e.g. multi_unit_skipped).
  --                  ADDED 2026-05-18 (ALTER TABLE — nullable for back-compat with
  --                  pre-existing rows that were written before the counter split).
  -- failed_count:    rows that errored out (api_failure et al). After the counter
  --                  split, this counts ONLY true failures — policy skips moved to
  --                  skipped_count.
  -- Invariant: completed_count + skipped_count + failed_count == address_count
  completed_count                  INT64 DEFAULT 0 NOT NULL,
  skipped_count                    INT64,
  failed_count                     INT64 DEFAULT 0 NOT NULL,

  -- Lifecycle
  created_at                       TIMESTAMP NOT NULL,
  started_at                       TIMESTAMP,
  completed_at                     TIMESTAMP,
  expires_at                       TIMESTAMP NOT NULL,        -- created_at + retention window

  -- Cost tracking (for unit economics analysis)
  geocoding_api_calls              INT64 DEFAULT 0 NOT NULL,
  solar_api_calls                  INT64 DEFAULT 0 NOT NULL,
  gemini_tokens_used               INT64 DEFAULT 0 NOT NULL,
  estimated_cost_usd               NUMERIC,

  -- Source context
  source_ip                        STRING,
  user_agent                       STRING
)
PARTITION BY DATE(created_at)
CLUSTER BY installer_id, status
OPTIONS (
  description = "Batch scoring job state. Frontend polls GET /batch-score/{job_id} which reads this table. Partitioned by created_at for cheap retention pruning.",
  partition_expiration_days = 90
);


-- ----------------------------------------------------------------------------
-- Batch scoring results (detail table)
-- Volume: one row per scored address per job (up to 500 per job)
-- Retention: tied to parent job lifecycle
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.leadlens.batch_results` (
  -- Composite key
  job_id                           STRING NOT NULL,
  result_index                     INT64 NOT NULL,            -- 0-based ordinal within the job

  -- Input
  input_address                    STRING NOT NULL,

  -- Geocoding result
  geocoded_lat                     FLOAT64,
  geocoded_lng                     FLOAT64,
  geocoder_place_id                STRING,
  geocoder_match_quality           STRING,                    -- 'ROOFTOP' | 'RANGE_INTERPOLATED' | etc

  -- Parcel resolution
  resolved_ain                     STRING,
  resolution_confidence            STRING,                    -- 'unit' | 'building' | 'unresolved'

  -- Scoring outcome
  scored_status                    STRING NOT NULL,           -- 'scored' | 'non_residential_422' | 'no_parcel_match' | 'api_failure'
  scored_at                        TIMESTAMP,
  error_message                    STRING,

  -- Final scores (NULL if scored_status != 'scored')
  priority_score                   NUMERIC,
  stream                           STRING,                    -- 'private' | 'dac_sash' | 'not_residential'

  -- Dimension breakdown (each may be NULL if unavailable)
  roof_potential                   NUMERIC,
  roof_potential_source            STRING,                    -- Provenance string
  roof_potential_confidence        STRING,                    -- 'precise' | 'approximate' | 'unavailable'

  income_qualified                 NUMERIC,
  income_qualified_source          STRING,
  income_qualified_confidence      STRING,

  ownership                        NUMERIC,
  ownership_label                  STRING,                    -- 'OWNER_OCCUPIED' | 'UNKNOWN_OR_TRUST' | etc
  ownership_tier                   STRING,                    -- '1a' | '1b' | '1c' | '2' .. '7'
  ownership_source                 STRING,
  ownership_confidence             STRING,

  bill_pain                        NUMERIC,
  bill_pain_utility                STRING,                    -- 'LADWP' | 'SCE' | 'unknown'
  bill_pain_source                 STRING,
  bill_pain_confidence             STRING,

  equity_strength                  NUMERIC,
  equity_strength_source           STRING,
  equity_strength_confidence       STRING,

  -- Phase 2 ghost dimensions (always NULL for now, structured for forward-compat)
  no_existing_solar                NUMERIC,
  no_existing_solar_status         STRING,                    -- 'unavailable' until Phase 2

  intent_signal                    NUMERIC,
  intent_signal_status             STRING,                    -- 'unavailable' until Phase 2

  -- Parcel context (denormalized for CSV export convenience)
  years_owned                      INT64,
  has_homeowners_exemption         BOOL,
  total_value                      NUMERIC,
  sqft_main                        INT64,
  year_built                       INT64,
  use_description                  STRING,

  -- Narrative
  gemini_narrative                 STRING,                    -- The full paragraph

  -- Verification URLs (computed; included in CSV export)
  verification_url_assessor        STRING,                    -- portal.assessor.lacounty.gov/parceldetail/...
  verification_url_sunroof         STRING,                    -- sunroof.withgoogle.com/...
  verification_url_satellite       STRING                     -- google.com/maps/...
)
PARTITION BY DATE(scored_at)
CLUSTER BY job_id, priority_score
OPTIONS (
  description = "Individual scored results within a batch job. Clustering by job_id + priority_score makes 'top N from this job' queries fast for the dashboard. All dimension columns include source+confidence triplets per truth-first design.",
  partition_expiration_days = 90
);


-- ----------------------------------------------------------------------------
-- Single-address score cache (for repeated lookups within a session)
-- Volume: bounded by distinct addresses scored
-- Retention: 30 days (rescore if data older than monthly roll cycle)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.leadlens.score_cache` (
  -- Cache key
  ain                              STRING NOT NULL,

  -- Cached payload (same columns as batch_results without job context)
  priority_score                   NUMERIC,
  stream                           STRING,

  roof_potential                   NUMERIC,
  income_qualified                 NUMERIC,
  ownership                        NUMERIC,
  ownership_label                  STRING,
  ownership_tier                   STRING,
  bill_pain                        NUMERIC,
  bill_pain_utility                STRING,
  equity_strength                  NUMERIC,

  gemini_narrative                 STRING,

  -- Cache metadata
  scored_at                        TIMESTAMP NOT NULL,
  expires_at                       TIMESTAMP NOT NULL,
  pipeline_version                 STRING NOT NULL,           -- e.g. 'phase-1.5e.1' — invalidate cache on pipeline upgrades
  attributes_ingest_id             STRING NOT NULL            -- Invalidate if the underlying data has been re-ingested
)
CLUSTER BY ain
OPTIONS (
  description = "Per-AIN score cache. Warm hits return in <500ms vs 4-8s cold. Cache invalidates on pipeline version bump or new attributes ingest."
);


-- ----------------------------------------------------------------------------
-- Audit trail: every score request, for unit-economics analysis and debugging
-- Volume: high (one row per API call)
-- Retention: 30 days
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.leadlens.score_audit` (
  audit_id                         STRING NOT NULL,           -- UUID
  request_at                       TIMESTAMP NOT NULL,

  -- Request shape
  endpoint                         STRING NOT NULL,           -- '/api/v1/score-lead' | '/api/v1/batch-score' | etc
  installer_id                     STRING,
  job_id                           STRING,                    -- If part of a batch
  input_address                    STRING,
  input_apn                        STRING,

  -- Resolution
  resolved_ain                     STRING,
  cache_hit                        BOOL NOT NULL,

  -- Outcome
  status_code                      INT64 NOT NULL,
  status_reason                    STRING,                    -- 'scored' | 'non_residential' | 'no_parcel' | 'api_failure_geocoding' | etc

  -- Latency breakdown (milliseconds)
  total_latency_ms                 INT64 NOT NULL,
  geocoding_latency_ms             INT64,
  parcel_lookup_latency_ms         INT64,
  solar_api_latency_ms             INT64,
  gemini_latency_ms                INT64,

  -- Cost tracking
  cost_usd                         NUMERIC,

  -- Pipeline version
  pipeline_version                 STRING NOT NULL,
  region_calibration_version       STRING NOT NULL            -- e.g. 'la_county_2026_q1'
)
PARTITION BY DATE(request_at)
CLUSTER BY endpoint, status_code
OPTIONS (
  description = "Every score request logged for unit-economics analysis. Partitioned by date for cheap retention pruning.",
  partition_expiration_days = 30
);


-- ----------------------------------------------------------------------------
-- TaxLens change detection events (Phase 2, schema reserved)
-- Volume: depends on detection cadence and confidence threshold
-- Retention: indefinite (audit trail for assessor accountability)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `sky-eye-496604.leadlens.change_events` (
  event_id                         STRING NOT NULL,           -- UUID
  ain                              STRING NOT NULL,

  -- Detection metadata
  detected_at                      TIMESTAMP NOT NULL,
  imagery_before_date              DATE NOT NULL,
  imagery_after_date               DATE NOT NULL,

  -- Change characterization
  change_type                      STRING,                    -- 'new_structure' | 'pool_added' | 'expansion' | 'demolition' | 'unknown'
  change_area_sqft_estimated       NUMERIC,
  confidence_score                 NUMERIC NOT NULL,          -- 0-1

  -- Cross-reference against permit database
  permit_check_status              STRING NOT NULL,           -- 'no_permit_in_window' | 'permit_matches' | 'permit_pending' | 'no_check_run'
  matching_permit_ids              ARRAY<STRING>,

  -- Evidence packet
  before_image_url                 STRING,                    -- GCS URL to rendered before tile
  after_image_url                  STRING,                    -- GCS URL to rendered after tile
  diff_image_url                   STRING,                    -- GCS URL to highlighted diff

  -- Pipeline provenance
  detection_model                  STRING NOT NULL,           -- 'alphaearth_embeddings_v1' | etc
  pipeline_version                 STRING NOT NULL,

  -- Workflow state
  review_status                    STRING NOT NULL,           -- 'auto_detected' | 'analyst_reviewed' | 'sent_to_jurisdiction' | 'resolved' | 'false_positive'
  reviewed_by                      STRING,
  reviewed_at                      TIMESTAMP,
  jurisdiction_notified_at         TIMESTAMP,
  resolution_notes                 STRING
)
PARTITION BY DATE(detected_at)
CLUSTER BY ain, confidence_score
OPTIONS (
  description = "Change detection events for TaxLens. Each event includes evidence packet URLs, permit cross-check result, and review workflow state. Phase 2 — schema reserved, table not yet populated."
);


-- ============================================================================
-- VIEWS (for common query patterns)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Active residential parcels (the dominant filter for LeadLens)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE VIEW `sky-eye-496604.parcels.la_county_residential` AS
SELECT *
FROM `sky-eye-496604.parcels.la_county`
WHERE is_residential = TRUE
  AND geom IS NOT NULL;


-- ----------------------------------------------------------------------------
-- DAC-SASH eligible parcels (for GRID Alternatives outreach)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE VIEW `sky-eye-496604.parcels.la_county_dac_sash` AS
SELECT
  p.*,
  dac.ces_percentile,
  dac.tract_geoid AS dac_tract_geoid
FROM `sky-eye-496604.parcels.la_county` p
LEFT JOIN `sky-eye-496604.parcels_raw.dac_tracts` dac
  ON ST_CONTAINS(dac.geom, ST_GEOGPOINT(p.center_lon, p.center_lat))
  AND (dac.is_sb535_dac = TRUE OR dac.is_tribal = TRUE)
WHERE p.is_residential = TRUE
  AND p.is_dac_sash_eligible_type = TRUE
  AND p.geom IS NOT NULL
  AND (p.is_taxable = FALSE OR dac.tract_geoid IS NOT NULL);  -- Union rule


-- ----------------------------------------------------------------------------
-- Latest score for each AIN (resolves cache + most recent batch hit)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE VIEW `sky-eye-496604.leadlens.latest_scores` AS
WITH cache_scores AS (
  SELECT
    ain,
    priority_score,
    stream,
    scored_at,
    'cache' AS score_source
  FROM `sky-eye-496604.leadlens.score_cache`
  WHERE expires_at > CURRENT_TIMESTAMP()
),
batch_scores AS (
  SELECT
    resolved_ain AS ain,
    priority_score,
    stream,
    scored_at,
    'batch' AS score_source
  FROM `sky-eye-496604.leadlens.batch_results`
  WHERE scored_status = 'scored'
    AND resolved_ain IS NOT NULL
),
combined AS (
  SELECT * FROM cache_scores
  UNION ALL
  SELECT * FROM batch_scores
),
ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY ain ORDER BY scored_at DESC) AS rn
  FROM combined
)
SELECT
  ain,
  priority_score,
  stream,
  scored_at,
  score_source
FROM ranked
WHERE rn = 1;


-- ============================================================================
-- INDEXES (BigQuery doesn't have traditional indexes; clustering is the lever)
-- All clustering decisions are inline in the CREATE TABLE statements above.
--
-- Key clustering rationales:
--
-- parcels.la_county: CLUSTER BY geom, is_residential, situs_zip
--   - geom first: spatial queries are the primary access pattern
--   - is_residential second: the most common filter on top of spatial
--   - situs_zip third: supports ZIP-based batch workflows
--
-- leadlens.batch_results: CLUSTER BY job_id, priority_score
--   - job_id first: "show me results for this job" is the primary query
--   - priority_score second: "top N from this job" sorts in cluster order
--
-- leadlens.score_cache: CLUSTER BY ain
--   - Direct AIN lookup is the only access pattern
-- ============================================================================


-- ============================================================================
-- INITIAL SEED DATA (run after table creation)
-- ============================================================================

-- Seed utility_rates (hand-maintained, ~5 rows)
INSERT INTO `sky-eye-496604.parcels_raw.utility_rates`
  (utility_name, representative_rate, tariff_variant, nem_regime, rate_source_note, confidence_level, effective_date, source_url, ingested_at)
VALUES
  ('LADWP', 0.27, 'R-1A', '1:1 retained', 'LADWP R-1A residential tier blend, 2026 schedule', 'approximate', '2026-01-01', 'https://www.ladwp.com/residential/electric-rates', CURRENT_TIMESTAMP()),
  ('SCE', 0.31, 'TOU-D-PRIME', 'NEM 3.0 (ACC export)', 'SCE TOU-D-PRIME blended off-peak + peak, NEM 3.0 default', 'approximate', '2026-01-01', 'https://www.sce.com/residential/rates', CURRENT_TIMESTAMP()),
  ('unknown', 0.30, NULL, NULL, 'Fallback flat-rate estimate for unidentified utilities', 'fallback', '2026-01-01', 'internal_fallback', CURRENT_TIMESTAMP());


-- ============================================================================
-- END OF DDL
-- ============================================================================
