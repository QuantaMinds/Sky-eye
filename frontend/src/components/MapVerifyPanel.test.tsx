import { render, screen } from "@testing-library/react"
import { MapVerifyPanel } from "@/components/MapVerifyPanel"
import { DEMO_SCORES } from "@/lib/demo-data"

describe("<MapVerifyPanel>", () => {
  it("renders 4 verify links for a result with APN", () => {
    render(<MapVerifyPanel result={DEMO_SCORES[0]} />)
    const links = screen.getAllByTestId("verify-link")
    expect(links).toHaveLength(4)
  })

  it("LA Assessor link uses dashed AIN", () => {
    render(<MapVerifyPanel result={DEMO_SCORES[0]} />)
    const link = screen.getByRole("link", { name: /LA County Assessor Portal/i })
    expect(link.getAttribute("href")).toContain("9999-001-001")
  })

  it("Google Maps satellite link includes the lat,lng", () => {
    render(<MapVerifyPanel result={DEMO_SCORES[0]} />)
    const link = screen.getByRole("link", { name: /Google Maps \(satellite\)/i })
    expect(link.getAttribute("href")).toContain("33.7625,-118.1551")
  })

  it("Sunroof link uses the lat/lng path", () => {
    render(<MapVerifyPanel result={DEMO_SCORES[0]} />)
    const link = screen.getByRole("link", { name: /Google Project Sunroof/i })
    expect(link.getAttribute("href")).toContain("sunroof.withgoogle.com/building/33.7625/-118.1551")
  })

  it("Census link uses the block_group_geoid when present", () => {
    render(<MapVerifyPanel result={DEMO_SCORES[0]} />)
    const link = screen.getByRole("link", { name: /Census ACS block group/i })
    expect(link.getAttribute("href")).toContain("1500000US060375759001")
  })

  it("omits the Assessor link when apn is missing", () => {
    const noApn = { ...DEMO_SCORES[0], apn: undefined }
    render(<MapVerifyPanel result={noApn} />)
    expect(screen.queryByRole("link", { name: /LA County Assessor Portal/i })).not.toBeInTheDocument()
  })
})
