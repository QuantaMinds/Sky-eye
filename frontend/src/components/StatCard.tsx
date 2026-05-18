import { Card, CardContent } from "@/components/ui/card"

interface Props {
  label: string
  value: string
  hint?: string
  testid?: string
}

export function StatCard({ label, value, hint, testid }: Props) {
  return (
    <Card data-testid={testid ?? "stat-card"} className="py-3">
      <CardContent className="px-4">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  )
}
