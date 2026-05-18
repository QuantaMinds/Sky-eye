import { render, screen } from "@testing-library/react"
import { StreamPill } from "@/components/StreamPill"

describe("<StreamPill>", () => {
  it("renders private installer label", () => {
    render(<StreamPill stream="private" />)
    expect(screen.getByTestId("stream-pill")).toHaveTextContent(/private installer stream/i)
  })
  it("renders DAC-SASH label", () => {
    render(<StreamPill stream="dac_sash" />)
    expect(screen.getByTestId("stream-pill")).toHaveTextContent(/dac-sash stream/i)
  })
  it("renders Not residential label", () => {
    render(<StreamPill stream="not_residential" />)
    expect(screen.getByTestId("stream-pill")).toHaveTextContent(/not residential/i)
  })
  it("renders unknown for null", () => {
    render(<StreamPill stream={null} />)
    const pill = screen.getByTestId("stream-pill")
    expect(pill).toHaveAttribute("data-stream", "unknown")
    expect(pill).toHaveTextContent(/unknown/i)
  })
})
