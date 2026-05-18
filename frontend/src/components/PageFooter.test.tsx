import { render, screen } from "@testing-library/react"
import { PageFooter } from "@/components/PageFooter"

describe("<PageFooter>", () => {
  it("renders the data sources joined with dot separators", () => {
    render(<PageFooter dataSources={["A", "B", "C"]} scoredAt="2026-05-18T15:00:00Z" />)
    expect(screen.getByTestId("page-footer")).toHaveTextContent("A · B · C")
  })

  it("renders dash when scoredAt is missing", () => {
    render(<PageFooter dataSources={[]} />)
    expect(screen.getByTestId("page-footer")).toHaveTextContent("Last scored: —")
  })

  it("includes latency when provided", () => {
    render(<PageFooter dataSources={[]} scoredAt="2026-05-18T15:00:00Z" latencyMs={4200} />)
    expect(screen.getByTestId("page-footer")).toHaveTextContent("4200 ms")
  })
})
