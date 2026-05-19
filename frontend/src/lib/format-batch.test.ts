import { describe, expect, it } from "vitest"
import { humanizeFailureReason, humanizeSkipReason } from "@/lib/format-batch"

describe("humanizeSkipReason", () => {
  it("renders the known multi_unit_skipped label", () => {
    expect(humanizeSkipReason("multi_unit_skipped")).toContain("Multi-unit")
  })

  it("falls back to title-cased status for unknown keys (never silently drops)", () => {
    // Catches the next conflation bug — if a new skip status ships without
    // a label, the raw status surfaces in the UI rather than vanishing.
    expect(humanizeSkipReason("out_of_county_skipped")).toBe("Out Of County Skipped")
  })
})

describe("humanizeFailureReason", () => {
  it("renders the known api_failure label", () => {
    expect(humanizeFailureReason("api_failure")).toMatch(/Transient API/i)
  })

  it("falls back to title-cased for unknown statuses", () => {
    expect(humanizeFailureReason("rate_limited_pending_retry")).toBe(
      "Rate Limited Pending Retry"
    )
  })
})
