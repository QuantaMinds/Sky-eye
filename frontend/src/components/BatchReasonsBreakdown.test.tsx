import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { BatchReasonsBreakdown } from "@/components/BatchReasonsBreakdown"

describe("<BatchReasonsBreakdown>", () => {
  it("renders nothing when both dicts are empty (no empty section headers)", () => {
    const { container } = render(<BatchReasonsBreakdown />)
    expect(container).toBeEmptyDOMElement()
  })

  it("renders the humanized multi_unit_skipped row with its count", () => {
    render(<BatchReasonsBreakdown skipReasons={{ multi_unit_skipped: 55 }} />)
    const row = screen.getByTestId("skip-row")
    expect(row).toHaveAttribute("data-key", "multi_unit_skipped")
    expect(row).toHaveTextContent("55")
    expect(row).toHaveTextContent(/Multi-unit/)
  })

  it("renders both sections when skip + failure dicts are populated", () => {
    render(
      <BatchReasonsBreakdown
        skipReasons={{ multi_unit_skipped: 55 }}
        failureReasons={{ api_failure: 7 }}
      />,
    )
    expect(screen.getByText("Excluded")).toBeInTheDocument()
    expect(screen.getByText("Failed")).toBeInTheDocument()
    expect(screen.getByTestId("skip-row")).toHaveTextContent("55")
    expect(screen.getByTestId("failure-row")).toHaveTextContent("7")
  })

  it("sorts entries by count descending within a section", () => {
    render(
      <BatchReasonsBreakdown
        skipReasons={{ multi_unit_skipped: 12, out_of_county_skipped: 30 }}
      />,
    )
    const rows = screen.getAllByTestId("skip-row")
    expect(rows[0]).toHaveAttribute("data-key", "out_of_county_skipped")
    expect(rows[1]).toHaveAttribute("data-key", "multi_unit_skipped")
  })
})
