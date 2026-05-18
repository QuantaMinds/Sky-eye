import { render, screen } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { ScoreResult } from "@/pages/ScoreResult"

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/score/:apn" element={<ScoreResult />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe("<ScoreResult>", () => {
  beforeEach(() => window.sessionStorage.clear())

  it("renders the full result page for a known demo APN", () => {
    renderAt("/score/9999001001")
    expect(screen.getByTestId("address-header")).toBeInTheDocument()
    expect(screen.getByTestId("stats-strip")).toBeInTheDocument()
    expect(screen.getByTestId("map-and-verify")).toBeInTheDocument()
    expect(screen.getByTestId("dimension-grid")).toBeInTheDocument()
    expect(screen.getByTestId("narrative-section")).toBeInTheDocument()
    expect(screen.getByTestId("page-footer")).toBeInTheDocument()
  })

  it("shows ScoreNotFound for an unknown APN", () => {
    renderAt("/score/1234567890")
    expect(screen.getByText(/No scored result for APN/i)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Back to home/i })).toBeInTheDocument()
  })

  it("uses dashed AIN in the address header for known APN", () => {
    renderAt("/score/9999001001")
    expect(screen.getByText(/APN: 9999-001-001/)).toBeInTheDocument()
  })

  it("renders 7 dimension cards total (5 active + 2 ghost)", () => {
    renderAt("/score/9999001001")
    expect(screen.getByTestId("dimension-roof_potential")).toBeInTheDocument()
    expect(screen.getByTestId("dimension-income_qualification")).toBeInTheDocument()
    expect(screen.getByTestId("dimension-ownership")).toBeInTheDocument()
    expect(screen.getByTestId("dimension-bill_pain")).toBeInTheDocument()
    expect(screen.getByTestId("dimension-equity_proxy")).toBeInTheDocument()
    expect(screen.getByTestId("dimension-no_existing_solar")).toHaveAttribute("data-tier", "ghost")
    expect(screen.getByTestId("dimension-intent_signal")).toHaveAttribute("data-tier", "ghost")
  })
})
