import { render, screen } from "@testing-library/react"
import { AddressHeader } from "@/components/AddressHeader"
import { DEMO_SCORES } from "@/lib/demo-data"

const demo = DEMO_SCORES[0]

describe("<AddressHeader>", () => {
  it("renders the formatted address as an h1", () => {
    render(<AddressHeader result={demo} />)
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(demo.address)
  })

  it("renders the APN with dashes", () => {
    render(<AddressHeader result={demo} />)
    expect(screen.getByText(/APN:/i)).toHaveTextContent("APN: 9999-001-001")
  })

  it("renders score badge with the score tier", () => {
    render(<AddressHeader result={demo} />)
    const badge = screen.getByTestId("score-badge")
    expect(badge).toHaveAttribute("data-tier", "high")
  })

  it("renders stream pill with the stream", () => {
    render(<AddressHeader result={demo} />)
    expect(screen.getByTestId("stream-pill")).toHaveAttribute("data-stream", "private")
  })

  it("shows the Demo badge when is_demo is true", () => {
    render(<AddressHeader result={demo} />)
    expect(screen.getByTestId("demo-badge")).toBeInTheDocument()
  })

  it("hides the Demo badge when is_demo is falsey", () => {
    render(<AddressHeader result={{ ...demo, is_demo: false }} />)
    expect(screen.queryByTestId("demo-badge")).not.toBeInTheDocument()
  })
})
