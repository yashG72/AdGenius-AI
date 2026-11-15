import { SparklesIcon } from "lucide-react"

import { cn } from "@/lib/utils"

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2 font-heading font-semibold tracking-tight", className)}>
      <span className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
        <SparklesIcon className="size-4" aria-hidden />
      </span>
      AdGenius<span className="text-primary">AI</span>
    </span>
  )
}
