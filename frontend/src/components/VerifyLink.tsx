import { ExternalLink } from "lucide-react"
import { cn } from "@/lib/utils"

interface Props {
  href: string
  label: string
  className?: string
  variant?: "inline" | "button"
}

export function VerifyLink({ href, label, className, variant = "inline" }: Props) {
  const base =
    variant === "button"
      ? "inline-flex items-center justify-between gap-2 rounded-lg border bg-background hover:bg-muted px-3 py-2 text-sm font-medium transition-colors"
      : "inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline underline-offset-2"

  return (
    <a
      data-testid="verify-link"
      data-href={href}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(base, className)}
    >
      <span>{label}</span>
      <ExternalLink className={variant === "button" ? "size-4" : "size-3"} aria-hidden="true" />
    </a>
  )
}
