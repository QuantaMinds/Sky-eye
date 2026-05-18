import { render, screen } from "@testing-library/react"
import { DimensionCard } from "@/components/DimensionCard"
import type { DimensionValue } from "@/types/score"

const dim: DimensionValue = { value: 0.83, source: "google_solar", note: "1,130 sqft south-facing" }

describe("<DimensionCard>", () => {
  it("renders the dimension label and rounded percent", () => {
    render(<DimensionCard name="roof_potential" dim={dim} />)
    expect(screen.getByText(/Roof Potential/i)).toBeInTheDocument()
    expect(screen.getByTestId("dimension-roof_potential")).toHaveTextContent("83")
  })

  it("renders the note when present", () => {
    render(<DimensionCard name="roof_potential" dim={dim} />)
    expect(screen.getByText(/1,130 sqft south-facing/i)).toBeInTheDocument()
  })

  it("renders source attribution", () => {
    render(<DimensionCard name="roof_potential" dim={dim} />)
    expect(screen.getByText(/Source: google_solar/i)).toBeInTheDocument()
  })

  it("renders verify link when verifyHref is provided", () => {
    render(<DimensionCard name="ownership" dim={dim} verifyHref="https://portal.assessor.lacounty.gov/parceldetail/7076-019-008" verifyLabel="LA Assessor" />)
    const link = screen.getByRole("link", { name: /LA Assessor/i })
    expect(link).toHaveAttribute("href", "https://portal.assessor.lacounty.gov/parceldetail/7076-019-008")
    expect(link).toHaveAttribute("target", "_blank")
  })

  it("does not render verify link when verifyHref is missing", () => {
    render(<DimensionCard name="roof_potential" dim={dim} />)
    expect(screen.queryByTestId("verify-link")).not.toBeInTheDocument()
  })

  it("marks tier high for >= 0.8", () => {
    render(<DimensionCard name="roof_potential" dim={dim} />)
    expect(screen.getByTestId("dimension-roof_potential")).toHaveAttribute("data-tier", "high")
  })

  it("marks tier unknown for null value", () => {
    render(<DimensionCard name="roof_potential" dim={{ value: null, source: "unavailable" }} />)
    expect(screen.getByTestId("dimension-roof_potential")).toHaveAttribute("data-tier", "unknown")
    expect(screen.getByTestId("dimension-roof_potential")).toHaveTextContent("—")
  })
})
