import { useState, useRef, useEffect } from "react"
import { Printer, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { getEnvConfig } from "@/lib/env"

interface Props {
  apn: string | null
}

export function PrintButton({ apn }: Props) {
  const [isLoading, setIsLoading] = useState(false)
  const objectUrls = useRef<string[]>([])

  useEffect(() => {
    return () => {
      objectUrls.current.forEach((url) => window.URL.revokeObjectURL(url))
    }
  }, [])

  const handleDownload = async () => {
    if (!apn) return
    setIsLoading(true)
    try {
      const config = getEnvConfig()
      const response = await fetch(`${config.apiBaseUrl}/generate-report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apn }),
      })

      if (!response.ok) {
        throw new Error("Failed to generate report")
      }

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      objectUrls.current.push(url)

      const a = document.createElement("a")
      a.href = url
      const disposition = response.headers.get("Content-Disposition")
      let filename = "lead_report.pdf"
      if (disposition && disposition.includes("filename=")) {
        const match = disposition.match(/filename="?([^";]+)"?/)
        if (match && match[1]) {
          filename = match[1]
        }
      }
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
    } catch (error) {
      console.error("Error downloading PDF:", error)
      alert("Failed to download report. Please try again.")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={handleDownload}
      disabled={!apn || isLoading}
      data-testid="print-button"
    >
      {isLoading ? (
        <Loader2 className="animate-spin" aria-hidden="true" />
      ) : (
        <Printer aria-hidden="true" />
      )}
      <span>{isLoading ? "Generating..." : "Print to PDF"}</span>
    </Button>
  )
}
