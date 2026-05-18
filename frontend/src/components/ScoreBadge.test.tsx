import { render, screen } from "@testing-library/react"
import { ScoreBadge } from "@/components/ScoreBadge"

describe("<ScoreBadge>", () => {
  it("renders the rounded percent and /100", () => {
    render(<ScoreBadge score={0.83} />)
    expect(screen.getByTestId("score-badge")).toHaveTextContent("83")
    expect(screen.getByTestId("score-badge")).toHaveTextContent("/100")
  })

  it("uses high tier for score >= 0.8", () => {
    render(<ScoreBadge score={0.83} />)
    expect(screen.getByTestId("score-badge")).toHaveAttribute("data-tier", "high")
  })

  it("uses medium tier for 0.6 <= score < 0.8", () => {
    render(<ScoreBadge score={0.71} />)
    expect(screen.getByTestId("score-badge")).toHaveAttribute("data-tier", "medium")
  })

  it("uses low tier for score < 0.6", () => {
    render(<ScoreBadge score={0.45} />)
    expect(screen.getByTestId("score-badge")).toHaveAttribute("data-tier", "low")
  })

  it("renders dash and unknown tier for null score", () => {
    render(<ScoreBadge score={null} />)
    const badge = screen.getByTestId("score-badge")
    expect(badge).toHaveTextContent("—")
    expect(badge).toHaveAttribute("data-tier", "unknown")
    expect(badge).not.toHaveTextContent("/100")
  })
})
