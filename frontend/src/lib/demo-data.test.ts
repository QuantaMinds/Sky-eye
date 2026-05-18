import { DEMO_SCORES, lookupDemoByApn } from "@/lib/demo-data"

describe("DEMO_SCORES", () => {
  it("contains exactly 3 demo entries", () => {
    expect(DEMO_SCORES).toHaveLength(3)
  })

  it("every entry is flagged as demo", () => {
    for (const s of DEMO_SCORES) {
      expect(s.is_demo).toBe(true)
    }
  })

  it("every entry has a unique 10-digit APN", () => {
    const apns = DEMO_SCORES.map((s) => s.apn ?? "")
    for (const apn of apns) {
      expect(apn).toMatch(/^\d{10}$/)
    }
    expect(new Set(apns).size).toBe(apns.length)
  })

  it("two ghost dimensions are null-valued on every entry", () => {
    for (const s of DEMO_SCORES) {
      expect(s.dimensions.no_existing_solar.value).toBeNull()
      expect(s.dimensions.intent_signal.value).toBeNull()
    }
  })

  it("five active dimensions have a numeric value on every entry", () => {
    const active = ["roof_potential", "income_qualification", "ownership", "bill_pain", "equity_proxy"] as const
    for (const s of DEMO_SCORES) {
      for (const k of active) {
        expect(typeof s.dimensions[k].value).toBe("number")
      }
    }
  })

  it("Boyle Heights entry is routed to dac_sash", () => {
    const boyle = DEMO_SCORES.find((s) => s.address.includes("Boyle"))
    expect(boyle?.stream).toBe("dac_sash")
    expect(boyle?.is_dac).toBe(true)
  })

  it("Belmont and Bixby entries route to private stream", () => {
    const belmont = DEMO_SCORES.find((s) => s.address.includes("Belmont"))
    const bixby = DEMO_SCORES.find((s) => s.address.includes("Bixby"))
    expect(belmont?.stream).toBe("private")
    expect(bixby?.stream).toBe("private")
  })
})

describe("lookupDemoByApn", () => {
  it("finds an entry by exact 10-digit APN", () => {
    expect(lookupDemoByApn("9999001001")?.address).toContain("Belmont")
  })
  it("accepts dashed APN input", () => {
    expect(lookupDemoByApn("9999-001-002")?.address).toContain("Bixby")
  })
  it("returns null for unknown APN", () => {
    expect(lookupDemoByApn("1234567890")).toBeNull()
  })
})
