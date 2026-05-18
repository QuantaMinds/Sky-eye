import { render, screen } from "@testing-library/react"
import { StatsStrip } from "@/components/StatsStrip"
import { DEMO_SCORES } from "@/lib/demo-data"

describe("<StatsStrip>", () => {
  it("renders 4 stat cards by testid", () => {
    render(<StatsStrip result={DEMO_SCORES[0]} />)
    expect(screen.getByTestId("stat-confidence")).toBeInTheDocument()
    expect(screen.getByTestId("stat-ownership")).toBeInTheDocument()
    expect(screen.getByTestId("stat-dac")).toBeInTheDocument()
    expect(screen.getByTestId("stat-ces")).toBeInTheDocument()
  })
})
