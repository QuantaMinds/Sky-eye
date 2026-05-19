/**
 * Humanize scored_status keys from the backend into UI-ready labels.
 *
 * The backend keeps reason dicts honest — raw scored_status strings, no
 * fake-zero entries. The UI translates them at the boundary so Tony's
 * dashboard reads "Multi-unit buildings excluded" instead of
 * "multi_unit_skipped" — without losing the underlying status as the
 * source of truth (lookups by status still work).
 *
 * Unknown keys fall through to a title-cased version of the raw status,
 * never silently dropped — surfacing the next conflation bug to the eye.
 */

const SKIP_LABELS: Record<string, string> = {
  multi_unit_skipped: "Multi-unit buildings excluded (different product category)",
}

const FAILURE_LABELS: Record<string, string> = {
  api_failure: "Transient API errors (retryable)",
}

function titleCase(key: string): string {
  return key
    .split("_")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : ""))
    .join(" ")
}

export function humanizeSkipReason(key: string): string {
  return SKIP_LABELS[key] ?? titleCase(key)
}

export function humanizeFailureReason(key: string): string {
  return FAILURE_LABELS[key] ?? titleCase(key)
}
