import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { MemoryRouter } from "react-router-dom"
import { BatchResultsTable } from "@/components/BatchResultsTable"
import type { BatchResultRow } from "@/types/batch"

function row(o: Partial<BatchResultRow> = {}): BatchResultRow {
  return {
    job_id: "j", result_index: 0, input_address: "1 A St", scored_status: "scored",
    priority_score: 0.5, resolved_ain: "1234567890", stream: "private", ...o,
  }
}

function withRouter(node: React.ReactNode) {
  return <MemoryRouter>{node}</MemoryRouter>
}

describe("<BatchResultsTable>", () => {
  it("shows the empty-state message when no rows scored", () => {
    render(withRouter(<BatchResultsTable results={[]} />))
    expect(screen.getByTestId("batch-results-empty")).toBeInTheDocument()
  })

  it("hides multi_unit_skipped and api_failure rows", () => {
    render(withRouter(<BatchResultsTable results={[
      row({ result_index: 0, scored_status: "multi_unit_skipped", priority_score: null, resolved_ain: null }),
      row({ result_index: 1, scored_status: "api_failure", priority_score: null, resolved_ain: null }),
      row({ result_index: 2, scored_status: "scored", priority_score: 0.7 }),
    ]} />))
    expect(screen.getAllByTestId("batch-row")).toHaveLength(1)
  })

  it("sorts scored rows by priority_score descending", () => {
    render(withRouter(<BatchResultsTable results={[
      row({ result_index: 0, priority_score: 0.45, resolved_ain: "1111111111" }),
      row({ result_index: 1, priority_score: 0.82, resolved_ain: "2222222222" }),
      row({ result_index: 2, priority_score: 0.71, resolved_ain: "3333333333" }),
    ]} />))
    const rows = screen.getAllByTestId("batch-row")
    expect(rows[0]).toHaveTextContent("82")
    expect(rows[1]).toHaveTextContent("71")
    expect(rows[2]).toHaveTextContent("45")
  })

  it("links the AIN cell to /score/:apn", () => {
    render(withRouter(<BatchResultsTable results={[row({ resolved_ain: "1234567890" })]} />))
    const link = screen.getByRole("link")
    expect(link).toHaveAttribute("href", "/score/1234567890")
    expect(link).toHaveTextContent("1234-567-890")
  })
})
