"use client"

import { useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { Skeleton } from "@/components/ui/skeleton"
import { api, unwrap } from "@/lib/api/client"
import type { ConceptSet } from "@/lib/api/types"
import { useOutput } from "@/lib/queries/campaigns"

import { ConceptCard } from "./concept-card"
import { VersionPicker } from "./version-picker"

/** All concept rounds (versions); the human-approved concept is marked "Selected". */
export function ConceptsView({ runId }: { runId: string }) {
  const latest = useOutput(runId, "concepts")
  const [version, setVersion] = useState<number | undefined>()
  const selected = useOutput(runId, "concepts", { version, enabled: version !== undefined })
  const approvals = useQuery({
    queryKey: ["run", runId, "approvals"],
    queryFn: () =>
      unwrap(api.GET("/api/v1/campaign-runs/{run_id}/approvals", { params: { path: { run_id: runId } } })),
  })
  const output = version === undefined ? latest.data : selected.data
  if (latest.isPending || !output) return <Skeleton className="h-96 rounded-xl" />

  const set = output.content as unknown as ConceptSet
  const chosen = approvals.data?.items.find((a) => a.status === "approved")?.decision?.concept_id as
    | string
    | undefined

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-muted-foreground">
          <span className="text-foreground">Core messaging:</span> {set.campaign_messaging}
        </p>
        <VersionPicker
          versions={latest.data?.versions ?? 1}
          value={output.version}
          onChange={(v) => setVersion(v === latest.data?.versions ? undefined : v)}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        {set.concepts.map((concept) => (
          <ConceptCard
            key={concept.concept_id}
            concept={concept}
            recommended={concept.concept_id === set.recommended_concept_id}
            chosen={output.version === latest.data?.versions && concept.concept_id === chosen}
          />
        ))}
      </div>
      <p className="text-sm text-muted-foreground">
        <span className="text-foreground">Strategist:</span> {set.recommendation_reasoning}
      </p>
    </div>
  )
}
