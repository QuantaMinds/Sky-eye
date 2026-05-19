import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { BatchStatusCounters } from "@/components/BatchStatusCounters"
import type { BatchStatusResponse } from "@/types/batch"

function makeStatus(overrides: Partial<BatchStatusResponse> = {}): BatchStatusResponse {
  return {
    job_id: "j",
    status: "complete",
    address_count: 100,
    completed_count: 38,
    skipped_count: 55,
    failed_count: 7,
    results: [],
    ...overrides,
  }
}

describe("<BatchStatusCounters>", () => {
  it("renders the 38 / 55 / 7 headline tree against a complete status", () => {
    render(<BatchStatusCounters status={makeStatus()} />)
    expect(screen.getByTestId("counter-total")).toHaveTextContent("100")
    expect(screen.getByTestId("counter-completed")).toHaveTextContent("38")
    expect(screen.getByTestId("counter-skipped")).toHaveTextContent("55")
    expect(screen.getByTestId("counter-failed")).toHaveTextContent("7")
  })

  it("does not show the invariant warning when counts add up", () => {
    render(<BatchStatusCounters status={makeStatus()} />)
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("surfaces an alert when counts don't sum to address_count (conflation guard)", () => {
    render(
      <BatchStatusCounters
        status={makeStatus({ completed_count: 30, skipped_count: 55, failed_count: 7 })}
      />,
    )
    expect(screen.getByRole("alert")).toHaveTextContent(/Counter invariant/)
  })

  it("does NOT show the invariant warning while still processing (counts in flux)", () => {
    render(
      <BatchStatusCounters
        status={makeStatus({ status: "processing", completed_count: 10, skipped_count: 0, failed_count: 0 })}
      />,
    )
    expect(screen.queryByRole("alert")).toBeNull()
  })
})
