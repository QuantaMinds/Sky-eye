import { DEMO_SCORES } from "@/lib/demo-data"
import { loadScore, saveScore } from "@/lib/session-store"

describe("session-store", () => {
  beforeEach(() => window.sessionStorage.clear())

  it("round-trips a score by APN", () => {
    saveScore(DEMO_SCORES[0])
    const loaded = loadScore("9999001001")
    expect(loaded?.address).toBe(DEMO_SCORES[0].address)
  })

  it("loads by dashed APN as well", () => {
    saveScore(DEMO_SCORES[0])
    expect(loadScore("9999-001-001")?.score).toBe(DEMO_SCORES[0].score)
  })

  it("returns null for unknown APN", () => {
    expect(loadScore("1111111111")).toBeNull()
  })

  it("no-ops without an APN on the result", () => {
    saveScore({ ...DEMO_SCORES[0], apn: undefined })
    expect(window.sessionStorage.length).toBe(0)
  })
})
