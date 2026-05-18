import {
  formatAIN,
  formatKw,
  formatScorePercent,
  formatTenureYears,
  formatUsd,
  scoreTier,
  unformatAIN,
} from "@/lib/format"

describe("formatAIN", () => {
  it("inserts dashes for a 10-digit AIN", () => {
    expect(formatAIN("7076019008")).toBe("7076-019-008")
  })
  it("strips non-digits before formatting", () => {
    expect(formatAIN("7076 019 008")).toBe("7076-019-008")
  })
  it("returns input unchanged when not 10 digits", () => {
    expect(formatAIN("123")).toBe("123")
  })
})

describe("unformatAIN", () => {
  it("strips dashes", () => {
    expect(unformatAIN("7076-019-008")).toBe("7076019008")
  })
})

describe("formatScorePercent", () => {
  it("rounds to nearest percent", () => {
    expect(formatScorePercent(0.836)).toBe("84")
  })
  it("returns dash for null", () => {
    expect(formatScorePercent(null)).toBe("—")
  })
})

describe("scoreTier", () => {
  it("returns high for >= 0.8", () => {
    expect(scoreTier(0.8)).toBe("high")
    expect(scoreTier(0.95)).toBe("high")
  })
  it("returns medium for 0.6 to 0.79", () => {
    expect(scoreTier(0.6)).toBe("medium")
    expect(scoreTier(0.79)).toBe("medium")
  })
  it("returns low for < 0.6", () => {
    expect(scoreTier(0.59)).toBe("low")
    expect(scoreTier(0)).toBe("low")
  })
  it("returns null for null", () => {
    expect(scoreTier(null)).toBeNull()
  })
})

describe("formatTenureYears", () => {
  it("formats positive years", () => {
    expect(formatTenureYears(51)).toBe("51 years")
  })
  it("returns dash for null", () => {
    expect(formatTenureYears(null)).toBe("—")
  })
})

describe("formatUsd", () => {
  it("formats whole dollars with comma", () => {
    expect(formatUsd(2400)).toBe("$2,400")
  })
  it("rounds to nearest 100 when asked", () => {
    expect(formatUsd(2437, { round: 100 })).toBe("$2,400")
  })
  it("returns dash for null", () => {
    expect(formatUsd(null)).toBe("—")
  })
})

describe("formatKw", () => {
  it("formats with one decimal and kW suffix", () => {
    expect(formatKw(7.2)).toBe("7.2 kW")
  })
  it("returns dash for null", () => {
    expect(formatKw(null)).toBe("—")
  })
})
