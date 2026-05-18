import { DEMO_SCORES } from "@/lib/demo-data"
import { verifyTargetFor } from "@/lib/dimension-verify"

const belmont = DEMO_SCORES[0]

describe("verifyTargetFor", () => {
  it("ownership routes to LA Assessor with dashed AIN", () => {
    const t = verifyTargetFor("ownership", belmont)
    expect(t?.href).toContain("portal.assessor.lacounty.gov")
    expect(t?.href).toContain("9999-001-001")
  })

  it("equity_proxy routes to LA Assessor too", () => {
    const t = verifyTargetFor("equity_proxy", belmont)
    expect(t?.href).toContain("portal.assessor.lacounty.gov")
  })

  it("roof_potential routes to Project Sunroof", () => {
    const t = verifyTargetFor("roof_potential", belmont)
    expect(t?.href).toContain("sunroof.withgoogle.com")
  })

  it("income_qualification routes to data.census.gov", () => {
    const t = verifyTargetFor("income_qualification", belmont)
    expect(t?.href).toContain("data.census.gov")
  })

  it("bill_pain routes to LADWP when note mentions LADWP", () => {
    const t = verifyTargetFor("bill_pain", belmont)
    expect(t?.href).toContain("ladwp.com")
  })

  it("ghost dimensions return null", () => {
    expect(verifyTargetFor("no_existing_solar", belmont)).toBeNull()
    expect(verifyTargetFor("intent_signal", belmont)).toBeNull()
  })

  it("ownership returns null when apn missing", () => {
    const noApn = { ...belmont, apn: undefined }
    expect(verifyTargetFor("ownership", noApn)).toBeNull()
  })
})
