import { Link } from "react-router-dom"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"

interface Props {
  apn?: string
}

export function ScoreNotFound({ apn }: Props) {
  return (
    <main className="mx-auto max-w-2xl px-4 py-12 space-y-6">
      <Alert>
        <AlertTitle>No scored result for APN {apn ?? "(none)"}</AlertTitle>
        <AlertDescription>
          A score is only fetchable by address right now — direct-by-APN lookup is a Phase 3
          backend feature. Go back to the home page and score the address.
        </AlertDescription>
      </Alert>
      <Button asChild>
        <Link to="/">Back to home</Link>
      </Button>
    </main>
  )
}
