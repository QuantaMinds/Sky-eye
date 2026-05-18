import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { DemoCard } from "@/components/DemoCard"
import { DEMO_SCORES } from "@/lib/demo-data"

describe("<DemoCard>", () => {
  it("renders address, dashed APN, and links to /score/:apn", () => {
    render(
      <MemoryRouter>
        <DemoCard result={DEMO_SCORES[0]} />
      </MemoryRouter>,
    )
    const link = screen.getByTestId("demo-card-9999001001")
    expect(link).toHaveAttribute("href", "/score/9999001001")
    expect(screen.getByText(/9999-001-001/)).toBeInTheDocument()
    expect(screen.getByText(DEMO_SCORES[0].address)).toBeInTheDocument()
  })
})
