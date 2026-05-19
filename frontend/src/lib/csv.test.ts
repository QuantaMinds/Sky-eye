import { describe, expect, it } from "vitest"
import { parseCsvAddresses } from "@/lib/csv"

describe("parseCsvAddresses", () => {
  it("splits one address per line and trims whitespace", () => {
    const r = parseCsvAddresses("  1 Main St \n2 Oak Ave\n")
    expect(r.addresses).toEqual(["1 Main St", "2 Oak Ave"])
    expect(r.blankLineCount).toBe(1) // trailing \n
    expect(r.duplicateCount).toBe(0)
  })

  it("dedupes case-insensitively, preserves first-occurrence order", () => {
    const r = parseCsvAddresses("1 Main St\n1 MAIN ST\n2 Oak Ave\n1 main st")
    expect(r.addresses).toEqual(["1 Main St", "2 Oak Ave"])
    expect(r.duplicateCount).toBe(2)
  })

  it("preserves the full line including embedded commas (real addresses)", () => {
    // Regression: v1 split at the first comma and silently stripped
    // city/state/ZIP, causing the backend to geocode the wrong location.
    const r = parseCsvAddresses(
      "2021 N Beverly Plaza, Long Beach, CA 90815\n100 Long Beach Blvd, Long Beach, CA 90802"
    )
    expect(r.addresses).toEqual([
      "2021 N Beverly Plaza, Long Beach, CA 90815",
      "100 Long Beach Blvd, Long Beach, CA 90802",
    ])
  })

  it("strips outer wrapping quotes (some CSV exports wrap each row)", () => {
    const r = parseCsvAddresses(
      '"1 Main St, Long Beach, CA"\n"2 Oak Ave, Long Beach, CA"'
    )
    expect(r.addresses).toEqual([
      "1 Main St, Long Beach, CA",
      "2 Oak Ave, Long Beach, CA",
    ])
  })

  it("caps at 500 addresses (mirrors backend MAX_BATCH)", () => {
    const lines = Array.from({ length: 600 }, (_, i) => `${i} Cap St`).join("\n")
    const r = parseCsvAddresses(lines)
    expect(r.addresses.length).toBe(500)
  })

  it("counts blank/whitespace-only lines as blank", () => {
    const r = parseCsvAddresses("1 Main St\n\n   \n2 Oak Ave")
    expect(r.addresses).toEqual(["1 Main St", "2 Oak Ave"])
    expect(r.blankLineCount).toBe(2)
  })
})
