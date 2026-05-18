import { render, screen } from "@testing-library/react"
import { NarrativeSection } from "@/components/NarrativeSection"

describe("<NarrativeSection>", () => {
  it("renders the narrative text", () => {
    render(<NarrativeSection narrative="A long-tenured home in Bixby Knolls." scoreConfidence={0.71} />)
    expect(screen.getByText(/long-tenured home in Bixby Knolls/i)).toBeInTheDocument()
  })

  it("renders the Gemini disclaimer and confidence percent", () => {
    render(<NarrativeSection narrative="x" scoreConfidence={0.71} />)
    expect(screen.getByText(/Gemini 2.5 Flash/i)).toBeInTheDocument()
    expect(screen.getByText(/71%/)).toBeInTheDocument()
  })
})
