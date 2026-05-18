import { CopyButton } from "@/components/CopyButton"
import { DemoBadge } from "@/components/DemoBadge"
import { PrintButton } from "@/components/PrintButton"
import { ScoreBadge } from "@/components/ScoreBadge"
import { ShareLinkButton } from "@/components/ShareLinkButton"
import { StreamPill } from "@/components/StreamPill"
import { formatAIN } from "@/lib/format"
import type { ScoreResponse } from "@/types/score"

interface Props {
  result: ScoreResponse
}

export function AddressHeader({ result }: Props) {
  const dashedApn = result.apn ? formatAIN(result.apn) : null

  return (
    <header
      data-testid="address-header"
      className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur px-4 py-4 md:px-8"
    >
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-xl font-bold tracking-tight md:text-2xl">
            {result.address}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {dashedApn && (
              <>
                <span className="font-mono">APN: {dashedApn}</span>
                <CopyButton text={dashedApn} label="Copy APN" />
              </>
            )}
            {result.is_demo && <DemoBadge />}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <StreamPill stream={result.stream} />
          <ScoreBadge score={result.score} />
          <div className="flex gap-2">
            <PrintButton />
            <ShareLinkButton />
          </div>
        </div>
      </div>
    </header>
  )
}
