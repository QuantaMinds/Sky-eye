import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { Landing } from "@/pages/Landing"

describe("<Landing>", () => {
  it("renders the LeadLens hero h1", () => {
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    )
    expect(screen.getByRole("heading", { level: 1, name: /LeadLens/i })).toBeInTheDocument()
  })

  it("renders 3 demo cards linking to /score/:apn", () => {
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>,
    )
    expect(screen.getByTestId("demo-card-9999001001")).toHaveAttribute("href", "/score/9999001001")
    expect(screen.getByTestId("demo-card-9999001002")).toHaveAttribute("href", "/score/9999001002")
    expect(screen.getByTestId("demo-card-9999001003")).toHaveAttribute("href", "/score/9999001003")
  })
})
