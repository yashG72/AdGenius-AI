import type { LucideIcon } from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string
  value: React.ReactNode
  hint?: React.ReactNode
  icon: LucideIcon
}) {
  return (
    <Card className="gap-0 py-4">
      <CardContent className="space-y-2 px-4">
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          {label}
          <Icon className="size-4" aria-hidden />
        </div>
        <p className="font-heading text-3xl font-semibold tabular-nums tracking-tight">{value}</p>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  )
}
