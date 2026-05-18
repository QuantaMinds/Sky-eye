import { cn } from "@/lib/utils"
import type { Stream } from "@/types/score"

interface Props {
  stream: Stream | null
}

const STYLES: Record<NonNullable<Stream>, { label: string; cls: string }> = {
  private: {
    label: "Private installer stream",
    cls: "bg-emerald-100 text-emerald-900 ring-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-100",
  },
  dac_sash: {
    label: "DAC-SASH stream",
    cls: "bg-sky-100 text-sky-900 ring-sky-300 dark:bg-sky-900/40 dark:text-sky-100",
  },
  not_residential: {
    label: "Not residential",
    cls: "bg-zinc-100 text-zinc-900 ring-zinc-300 dark:bg-zinc-800 dark:text-zinc-100",
  },
}

export function StreamPill({ stream }: Props) {
  const spec = stream ? STYLES[stream] : { label: "Stream unknown", cls: "bg-muted text-muted-foreground ring-border" }
  return (
    <span
      data-testid="stream-pill"
      data-stream={stream ?? "unknown"}
      className={cn("inline-flex items-center rounded-full ring-1 px-2.5 py-0.5 text-xs font-medium", spec.cls)}
    >
      {spec.label}
    </span>
  )
}
