import { render, screen } from "@testing-library/react"
import { GhostDimensionCard } from "@/components/GhostDimensionCard"

describe("<GhostDimensionCard>", () => {
  it("renders the dimension label and 'Phase 2 — coming soon'", () => {
    render(<GhostDimensionCard name="no_existing_solar" />)
    expect(screen.getByText(/Existing Solar Detection/i)).toBeInTheDocument()
    expect(screen.getByText(/Phase 2 — coming soon/i)).toBeInTheDocument()
  })

  it("marks itself as ghost tier and aria-disabled", () => {
    render(<GhostDimensionCard name="intent_signal" />)
    const card = screen.getByTestId("dimension-intent_signal")
    expect(card).toHaveAttribute("data-tier", "ghost")
    expect(card).toHaveAttribute("aria-disabled", "true")
  })

  it("does not render any verify link", () => {
    render(<GhostDimensionCard name="intent_signal" />)
    expect(screen.queryByTestId("verify-link")).not.toBeInTheDocument()
  })
})
