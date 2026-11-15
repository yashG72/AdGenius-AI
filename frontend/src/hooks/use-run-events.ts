"use client"

import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import type { AgentStep, RunDetail, RunStatus } from "@/lib/api/types"
import { campaignKeys } from "@/lib/queries/campaigns"
import { streamEvents } from "@/lib/sse"

type StatusEvent = {
  status: RunStatus
  overall_score: number | null
  error_message: string | null
  pending_approval_id: string | null
}

/**
 * Subscribe to a run's live event stream while it is active.
 *
 * - each `agent` event is appended straight into the cached run detail (instant UI),
 * - each `status` change refetches the run (pending approval, outputs, score),
 * - the stream closes on `end`; a paused run (awaiting approval) keeps listening so the
 *   UI picks up the resume as soon as someone decides.
 */
export function useRunEvents(runId: string, enabled: boolean): { connected: boolean } {
  const queryClient = useQueryClient()
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    const key = campaignKeys.run(runId)

    void streamEvents(`/api/v1/campaign-runs/${runId}/events`, {
      signal: controller.signal,
      finalEvent: "end",
      onMessage: ({ event, data }) => {
        setConnected(true)
        if (event === "agent") {
          const step = data as AgentStep
          queryClient.setQueryData<RunDetail>(key, (run) =>
            run && !run.agent_runs.some((s) => s.sequence === step.sequence)
              ? { ...run, agent_runs: [...run.agent_runs, step] }
              : run,
          )
          // A finished agent may have produced a new output version.
          void queryClient.invalidateQueries({ queryKey: ["run", runId, "output"] })
        } else if (event === "status" || event === "end") {
          const status = data as StatusEvent
          queryClient.setQueryData<RunDetail>(key, (run) =>
            run ? { ...run, status: status.status, overall_score: status.overall_score } : run,
          )
          void queryClient.invalidateQueries({ queryKey: key })
          void queryClient.invalidateQueries({ queryKey: campaignKeys.evaluation(runId) })
        }
      },
    }).finally(() => setConnected(false))

    return () => controller.abort()
  }, [runId, enabled, queryClient])

  return { connected }
}
