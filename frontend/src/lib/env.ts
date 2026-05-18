export function getGmapsKey(): string | null {
  const key = import.meta.env.VITE_GMAPS_KEY
  if (typeof key === "string" && key.length > 0) return key
  return null
}

export function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL ?? ""
}
