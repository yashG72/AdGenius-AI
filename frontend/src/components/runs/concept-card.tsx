import { StarIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { Concept } from "@/lib/api/types"
import { cn } from "@/lib/utils"

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{value}</dd>
    </div>
  )
}

export function ConceptCard({
  concept,
  recommended,
  selected,
  chosen,
  onSelect,
}: {
  concept: Concept
  recommended?: boolean
  selected?: boolean
  chosen?: boolean
  onSelect?: () => void
}) {
  const interactive = !!onSelect
  const Wrapper = interactive ? "button" : "div"
  return (
    <Wrapper
      {...(interactive ? { type: "button" as const, onClick: onSelect, "aria-pressed": selected } : {})}
      className={cn(
        "flex h-full flex-col gap-4 rounded-xl border bg-card p-5 text-left transition-colors",
        interactive && "hover:border-primary/50",
        selected || chosen ? "border-primary ring-1 ring-primary/40" : "border-border",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-primary">{concept.concept_id}</p>
          <h3 className="font-heading text-lg leading-snug font-semibold">{concept.title}</h3>
        </div>
        <div className="flex flex-col items-end gap-1">
          {recommended && (
            <Badge className="gap-1">
              <StarIcon className="size-3" aria-hidden /> Recommended
            </Badge>
          )}
          {chosen && <Badge variant="secondary">Selected</Badge>}
        </div>
      </div>
      <blockquote className="border-l-2 border-primary/60 pl-3 text-sm italic">{concept.opening_hook}</blockquote>
      <dl className="grid gap-3">
        <Row label="Core idea" value={concept.core_idea} />
        <Row label="Creative angle" value={concept.creative_angle} />
        <Row label="Target emotion" value={concept.target_emotion} />
        <Row label="Key message" value={concept.key_message} />
        <Row label="USP" value={concept.unique_selling_proposition} />
        <Row label="Call to action" value={concept.call_to_action} />
      </dl>
      <details className="mt-auto text-sm text-muted-foreground">
        <summary className="cursor-pointer select-none hover:text-foreground">Why this works</summary>
        <p className="mt-2">{concept.reasoning}</p>
        <p className="mt-2">
          <span className="text-foreground">Storytelling:</span> {concept.storytelling_approach}
        </p>
      </details>
    </Wrapper>
  )
}
