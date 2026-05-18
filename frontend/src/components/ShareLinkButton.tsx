import { useState } from "react"
import { Check, Share2 } from "lucide-react"
import { Button } from "@/components/ui/button"

export function ShareLinkButton() {
  const [shared, setShared] = useState(false)

  async function handleClick() {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setShared(true)
      window.setTimeout(() => setShared(false), 1500)
    } catch {
      // Truth-first: do not show fake success.
    }
  }

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={handleClick}
      data-testid="share-link-button"
      data-shared={shared}
    >
      {shared ? <Check aria-hidden="true" /> : <Share2 aria-hidden="true" />}
      <span>{shared ? "Link copied" : "Share link"}</span>
    </Button>
  )
}
