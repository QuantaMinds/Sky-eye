import {
  assessorPortalUrl,
  calEnviroScreenUrl,
  censusAcsBlockGroupUrl,
  googleSatelliteUrl,
  ladwpRateSheetUrl,
  projectSunroofUrl,
  sceRateSheetUrl,
  utilityRateSheetUrl,
} from "@/lib/verify-urls"

describe("assessorPortalUrl", () => {
  it("uses dashed AIN format", () => {
    expect(assessorPortalUrl("7076019008")).toBe(
      "https://portal.assessor.lacounty.gov/parceldetail/7076-019-008",
    )
  })
  it("normalizes already-dashed AIN", () => {
    expect(assessorPortalUrl("7076-019-008")).toBe(
      "https://portal.assessor.lacounty.gov/parceldetail/7076-019-008",
    )
  })
})

describe("googleSatelliteUrl", () => {
  it("embeds lat/lng with zoom-19 satellite tile data param", () => {
    const url = googleSatelliteUrl(33.78, -118.15)
    expect(url).toContain("33.78,-118.15")
    expect(url).toContain("19z")
    expect(url).toContain("!1e3")
  })
})

describe("projectSunroofUrl", () => {
  it("uses lat/lng building path", () => {
    expect(projectSunroofUrl(33.78, -118.15)).toBe(
      "https://sunroof.withgoogle.com/building/33.78/-118.15/details",
    )
  })
})

describe("censusAcsBlockGroupUrl", () => {
  it("encodes a block-group GEOID into the data.census.gov g param", () => {
    const url = censusAcsBlockGroupUrl("060375759001")
    expect(url).toContain("1500000US060375759001")
    expect(url).toContain("B19013")
  })
  it("falls back to generic ACS table when no geoid", () => {
    expect(censusAcsBlockGroupUrl(null)).not.toContain("1500000US")
  })
})

describe("calEnviroScreenUrl", () => {
  it("returns the SB-535 landing page", () => {
    expect(calEnviroScreenUrl()).toContain("oehha.ca.gov")
  })
})

describe("utility rate sheet URLs", () => {
  it("returns LADWP for LADWP utility", () => {
    expect(utilityRateSheetUrl("LADWP")).toBe(ladwpRateSheetUrl())
  })
  it("returns SCE for SCE utility", () => {
    expect(utilityRateSheetUrl("SCE")).toBe(sceRateSheetUrl())
  })
  it("returns CPUC fallback for unknown utility", () => {
    expect(utilityRateSheetUrl("unknown")).toContain("cpuc.ca.gov")
  })
})
