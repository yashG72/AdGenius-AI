import { Loader2Icon } from "lucide-react"

import { cn } from "@/lib/utils"
import { titleCase } from "@/lib/format"

type Tone = "neutral" | "progress" | "success" | "warning" | "danger"

const TONES: Record<string, Tone> = {
  // documents
  pending: "progress",
  processing: "progress",
  indexed: "success",
  failed: "danger",
  // campaign runs
  queued: "progress",
  running: "progress",
  awaiting_approval: "warning",
  completed: "success",
  needs_review: "warning",
  concepts_rejected: "neutral",
}

const STYLES: Record<Tone, string> = {
  neutral: "border-border bg-muted text-muted-foreground",
  progress: "border-sky-500/30 bg-sky-500/10 text-sky-300",
  success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  warning: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  danger: "border-red-500/30 bg-red-500/10 text-red-300",
}

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const tone = TONES[status] ?? "neutral"
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        STYLES[tone],
        className,
      )}
    >
      {tone === "progress" && <Loader2Icon className="size-3 animate-spin" aria-hidden />}
      {titleCase(status)}
    </span>
  )
}
