import { Printer } from "lucide-react"
import { Button } from "@/components/ui/button"

export function PrintButton() {
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={() => window.print()}
      data-testid="print-button"
    >
      <Printer aria-hidden="true" />
      <span>Print to PDF</span>
    </Button>
  )
}
