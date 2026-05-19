/**
 * Parse pasted text or an uploaded plain-text address list into a deduped
 * list of addresses. One full address per line, commas INSIDE the address
 * are preserved (`"123 Main St, Long Beach, CA 90802"` stays intact).
 *
 * Why the whole line, not the first comma-separated cell: real US
 * addresses contain commas as part of their canonical form, and the
 * common case for this dashboard is a paste of fully-qualified addresses.
 * Splitting at the first comma silently stripped city/state/ZIP and the
 * backend then geocoded the wrong location (see Phase 4 v1 bug found
 * 2026-05-19 on "2021 N Beverly Plaza, Long Beach, CA 90815").
 *
 * Multi-column CSV with the address in column 1 is NOT supported in v1.
 * If we add it later: detect quoting (`"123 Main St, LB, CA",extra`) and
 * route those through a proper CSV parser. Until then, single-address-
 * per-line is the contract.
 */

export interface CsvParseResult {
  addresses: string[]
  duplicateCount: number
  blankLineCount: number
}

const MAX_ADDRESSES = 500 // mirror api/models/batch.MAX_BATCH

export function parseCsvAddresses(input: string): CsvParseResult {
  const seen = new Set<string>()
  const addresses: string[] = []
  let blankLineCount = 0
  let duplicateCount = 0

  for (const rawLine of input.split(/\r?\n/)) {
    // Whole line is the address; strip outer quotes if present (some
    // exports wrap each row in "...").
    const trimmed = rawLine.trim().replace(/^"(.*)"$/, "$1").trim()
    if (!trimmed) {
      blankLineCount += 1
      continue
    }
    const key = trimmed.toLowerCase()
    if (seen.has(key)) {
      duplicateCount += 1
      continue
    }
    seen.add(key)
    addresses.push(trimmed)
    if (addresses.length >= MAX_ADDRESSES) break
  }
  return { addresses, duplicateCount, blankLineCount }
}

export async function readFileAsText(file: File): Promise<string> {
  return await file.text()
}
