import { DEMO_SCORES } from "@/lib/demo-data"
import { statsFor } from "@/lib/stats"

describe("statsFor", () => {
  it("returns 4 stat items", () => {
    expect(statsFor(DEMO_SCORES[0])).toHaveLength(4)
  })

  it("labels DAC eligibility Yes for dac_sash stream entry", () => {
    const boyle = DEMO_SCORES.find((s) => s.stream === "dac_sash")!
    const stats = statsFor(boyle)
    expect(stats.find((s) => s.testid === "stat-dac")?.value).toBe("Yes")
  })

  it("labels DAC eligibility No for non-DAC entries", () => {
    const belmont = DEMO_SCORES.find((s) => s.address.includes("Belmont"))!
    const stats = statsFor(belmont)
    expect(stats.find((s) => s.testid === "stat-dac")?.value).toBe("No")
  })

  it("maps ownership 0.95 to High", () => {
    const result = { ...DEMO_SCORES[0] }
    result.dimensions = { ...result.dimensions, ownership: { value: 0.95, source: "demo" } }
    const stat = statsFor(result).find((s) => s.testid === "stat-ownership")
    expect(stat?.value).toBe("High")
  })

  it("maps ownership 0.62 to Medium", () => {
    const result = { ...DEMO_SCORES[0] }
    result.dimensions = { ...result.dimensions, ownership: { value: 0.62, source: "demo" } }
    const stat = statsFor(result).find((s) => s.testid === "stat-ownership")
    expect(stat?.value).toBe("Medium")
  })

  it("maps null ownership to Unverified", () => {
    const result = { ...DEMO_SCORES[0] }
    result.dimensions = { ...result.dimensions, ownership: { value: null, source: "unavailable" } }
    const stat = statsFor(result).find((s) => s.testid === "stat-ownership")
    expect(stat?.value).toBe("Unverified")
  })
})
