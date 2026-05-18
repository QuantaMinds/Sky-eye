import { render, screen } from "@testing-library/react"
import { DimensionGrid } from "@/components/DimensionGrid"
import { DEMO_SCORES } from "@/lib/demo-data"

describe("<DimensionGrid>", () => {
  it("renders 5 active and 2 ghost dimension cards", () => {
    render(<DimensionGrid result={DEMO_SCORES[0]} />)
    const active = [
      "dimension-roof_potential",
      "dimension-income_qualification",
      "dimension-ownership",
      "dimension-bill_pain",
      "dimension-equity_proxy",
    ]
    for (const id of active) {
      expect(screen.getByTestId(id)).toHaveAttribute("data-tier", expect.stringMatching(/high|medium|low/))
    }
    expect(screen.getByTestId("dimension-no_existing_solar")).toHaveAttribute("data-tier", "ghost")
    expect(screen.getByTestId("dimension-intent_signal")).toHaveAttribute("data-tier", "ghost")
  })

  it("ownership card has an LA Assessor verify link", () => {
    render(<DimensionGrid result={DEMO_SCORES[0]} />)
    const ownership = screen.getByTestId("dimension-ownership")
    const link = ownership.querySelector("a[data-testid='verify-link']") as HTMLAnchorElement | null
    expect(link?.getAttribute("href")).toContain("portal.assessor.lacounty.gov")
  })
})
