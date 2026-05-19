/**
 * Parse pasted text or an uploaded CSV file into a deduped list of
 * addresses. The /batch-score endpoint accepts a flat string[] (the row
 * structure of the CSV is ignored) so the rule is: each line is one
 * address, ignore blank lines, trim each, deduplicate (case-insensitive)
 * preserving first-occurrence order.
 *
 * Single-column CSVs work as-is. Multi-column CSVs use the first column
 * only — Phase 4 dashboard does not support column mapping yet (the
 * common batch case for Tony's pilot is one address per line).
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
    const firstCell = rawLine.split(",")[0] ?? ""
    const trimmed = firstCell.trim().replace(/^"|"$/g, "").trim()
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
