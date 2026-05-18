import type { ScoreResponse } from "@/types/score"

const KEY_PREFIX = "leadlens:score:"

export function saveScore(result: ScoreResponse): void {
  if (typeof window === "undefined" || !result.apn) return
  try {
    window.sessionStorage.setItem(KEY_PREFIX + result.apn, JSON.stringify(result))
  } catch {
    // Storage may be unavailable (private mode quota etc.) — fail silently.
  }
}

export function loadScore(apn: string): ScoreResponse | null {
  if (typeof window === "undefined") return null
  try {
    const raw = window.sessionStorage.getItem(KEY_PREFIX + apn.replace(/\D/g, ""))
    if (!raw) return null
    return JSON.parse(raw) as ScoreResponse
  } catch {
    return null
  }
}
