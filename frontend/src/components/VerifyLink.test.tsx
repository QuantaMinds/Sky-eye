import { render, screen } from "@testing-library/react"
import { VerifyLink } from "@/components/VerifyLink"

describe("<VerifyLink>", () => {
  it("renders an anchor with target=_blank and noopener noreferrer", () => {
    render(<VerifyLink href="https://example.com" label="Verify" />)
    const link = screen.getByRole("link", { name: /verify/i })
    expect(link).toHaveAttribute("href", "https://example.com")
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
  })

  it("forwards the label as visible text", () => {
    render(<VerifyLink href="https://example.com" label="LA Assessor Portal" />)
    expect(screen.getByText(/LA Assessor Portal/i)).toBeInTheDocument()
  })
})
