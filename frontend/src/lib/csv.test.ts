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

  it("uses first CSV column when row has multiple commas", () => {
    const r = parseCsvAddresses("1 Main St,90210,extra\n2 Oak Ave,foo")
    expect(r.addresses).toEqual(["1 Main St", "2 Oak Ave"])
  })

  it("strips wrapping quotes from CSV cells", () => {
    const r = parseCsvAddresses('"1 Main St"\n"2 Oak Ave"')
    expect(r.addresses).toEqual(["1 Main St", "2 Oak Ave"])
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
