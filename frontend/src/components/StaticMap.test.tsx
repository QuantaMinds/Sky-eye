import { render, screen } from "@testing-library/react"
import { StaticMap } from "@/components/StaticMap"

describe("<StaticMap>", () => {
  it("renders unavailable placeholder when VITE_GMAPS_KEY is missing", () => {
    vi.stubEnv("VITE_GMAPS_KEY", "")
    render(<StaticMap lat={33.78} lng={-118.15} />)
    expect(screen.getByTestId("static-map-unavailable")).toBeInTheDocument()
    expect(screen.queryByTestId("static-map")).not.toBeInTheDocument()
    vi.unstubAllEnvs()
  })

  it("renders a Google Static Maps img with the key and coords when set", () => {
    vi.stubEnv("VITE_GMAPS_KEY", "fake-key-xyz")
    render(<StaticMap lat={33.78} lng={-118.15} />)
    const img = screen.getByTestId("static-map")
    const src = img.getAttribute("src") ?? ""
    expect(src).toContain("maps.googleapis.com/maps/api/staticmap")
    expect(src).toContain("center=33.78%2C-118.15")
    expect(src).toContain("key=fake-key-xyz")
    expect(src).toContain("maptype=satellite")
    vi.unstubAllEnvs()
  })
})
