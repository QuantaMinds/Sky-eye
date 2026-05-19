import { describe, expect, it, vi } from "vitest"

import { getBatchExportUrl } from "@/lib/api-batch"

// vite resolves import.meta.env.VITE_API_BASE_URL at build time; under
// vitest it's undefined, so getApiBaseUrl returns "" and the URL is
// relative to the page origin. That's the dev default and the contract
// we want to test against.

describe("getBatchExportUrl", () => {
  it("appends ?format=csv and percent-encodes the job id", () => {
    const url = getBatchExportUrl("abc 123/xx")
    expect(url).toContain("/api/v1/batch-score/")
    expect(url).toContain("/export?format=csv")
    expect(url).toContain("abc%20123%2Fxx")
  })

  it("uses VITE_API_BASE_URL when set", () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.com")
    try {
      const url = getBatchExportUrl("job-1")
      expect(url).toBe(
        "https://api.example.com/api/v1/batch-score/job-1/export?format=csv"
      )
    } finally {
      vi.unstubAllEnvs()
    }
  })
})
