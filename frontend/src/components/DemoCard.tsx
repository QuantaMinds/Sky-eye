import { Link } from "react-router-dom"
import { Card, CardContent } from "@/components/ui/card"
import { ScoreBadge } from "@/components/ScoreBadge"
import { StreamPill } from "@/components/StreamPill"
import { formatAIN } from "@/lib/format"
import type { ScoreResponse } from "@/types/score"

interface Props {
  result: ScoreResponse
}

export function DemoCard({ result }: Props) {
  const apn = result.apn ?? ""
  return (
    <Link
      to={`/score/${apn}`}
      data-testid={`demo-card-${apn}`}
      className="block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <Card className="h-full transition-shadow hover:shadow-md">
        <CardContent className="space-y-3 px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm font-medium leading-snug">{result.address}</p>
            <ScoreBadge score={result.score} size="sm" />
          </div>
          <p className="font-mono text-xs text-muted-foreground">APN {formatAIN(apn)}</p>
          <div className="flex flex-wrap gap-2">
            <StreamPill stream={result.stream} />
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}
