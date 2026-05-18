import { AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"

interface Props {
  className?: string
}

export function DemoBadge({ className }: Props) {
  return (
    <span
      data-testid="demo-badge"
      className={cn(
        "inline-flex items-center gap-1 rounded-full bg-amber-100 text-amber-900 ring-1 ring-amber-300 px-2 py-0.5 text-xs font-medium",
        "dark:bg-amber-900/40 dark:text-amber-100 dark:ring-amber-700",
        className,
      )}
    >
      <AlertCircle className="size-3" aria-hidden="true" />
      <span>Demo data — not a live lookup</span>
    </span>
  )
}
