import { getGmapsKey } from "@/lib/env"

interface Props {
  lat: number
  lng: number
  zoom?: number
  width?: number
  height?: number
  alt?: string
}

export function StaticMap({ lat, lng, zoom = 19, width = 640, height = 480, alt }: Props) {
  const key = getGmapsKey()

  if (!key) {
    return (
      <div
        data-testid="static-map-unavailable"
        role="status"
        className="flex aspect-[4/3] w-full items-center justify-center rounded-lg border border-dashed bg-muted/30 text-center text-sm text-muted-foreground p-6"
      >
        <p>
          Map unavailable — set <code className="font-mono text-xs">VITE_GMAPS_KEY</code> in
          <code className="font-mono text-xs ml-1">frontend/.env</code>.
        </p>
      </div>
    )
  }

  const params = new URLSearchParams({
    center: `${lat},${lng}`,
    zoom: String(zoom),
    size: `${width}x${height}`,
    scale: "2",
    maptype: "satellite",
    markers: `color:red|${lat},${lng}`,
    key,
  })

  return (
    <img
      data-testid="static-map"
      src={`https://maps.googleapis.com/maps/api/staticmap?${params.toString()}`}
      alt={alt ?? `Satellite view of ${lat.toFixed(5)}, ${lng.toFixed(5)}`}
      width={width}
      height={height}
      loading="lazy"
      className="w-full rounded-lg border bg-muted"
    />
  )
}
