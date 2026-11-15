"use client"

import {
  CheckIcon,
  CircleDashedIcon,
  CircleSlashIcon,
  Loader2Icon,
  PauseIcon,
  RadioIcon,
  RotateCcwIcon,
  XIcon,
} from "lucide-react"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { AgentStep, RunStatus } from "@/lib/api/types"
import { ACTIVE_STATUSES } from "@/lib/api/types"
import { formatDuration, titleCase } from "@/lib/format"
import { cn } from "@/lib/utils"

type StageState = "done" | "current" | "waiting" | "failed" | "skipped" | "pending"

/** The workflow's stages, each finished by its last agent. Order mirrors the LangGraph. */
const STAGES: { label: string; agents: string[]; doneWhen: string }[] = [
  { label: "Plan", agents: ["campaign_manager"], doneWhen: "campaign_manager" },
  { label: "Research", agents: ["brand_research", "competitor_research", "merge_research"], doneWhen: "merge_research" },
  { label: "Concepts", agents: ["creative_strategist"], doneWhen: "creative_strategist" },
  { label: "Your approval", agents: ["concept_approval"], doneWhen: "concept_approval" },
  { label: "Script", agents: ["scriptwriter"], doneWhen: "scriptwriter" },
  { label: "Storyboard", agents: ["visual_director"], doneWhen: "visual_director" },
  { label: "Critic", agents: ["critic", "revise"], doneWhen: "critic" },
  { label: "Final", agents: ["finalize"], doneWhen: "finalize" },
]

const AGENT_LABELS: Record<string, string> = {
  campaign_manager: "Campaign Manager",
  brand_research: "Brand Research",
  competitor_research: "Competitor Intelligence",
  merge_research: "Research merge",
  creative_strategist: "Creative Strategist",
  concept_approval: "Concept approval",
  scriptwriter: "Scriptwriter",
  visual_director: "Visual Director",
  critic: "Critic",
  revise: "Revision request",
  finalize: "Finalize",
}
export const agentLabel = (agent: string) => AGENT_LABELS[agent] ?? titleCase(agent)

function stageStates(steps: AgentStep[], status: RunStatus): StageState[] {
  const seen = new Set(steps.map((s) => s.agent))
  // A rejected concept round re-runs the strategist after approval; take the latest state.
  let firstOpen = STAGES.findIndex((stage) => !seen.has(stage.doneWhen))
  const revising = steps.at(-1)?.agent === "revise"
  if (revising) firstOpen = STAGES.findIndex((s) => s.label === "Script")
  return STAGES.map((stage, i) => {
    if (status === "concepts_rejected" && i > 3) return "skipped"
    if (firstOpen === -1 || i < firstOpen) return "done"
    if (i > firstOpen) return "pending"
    if (status === "awaiting_approval") return "waiting"
    if (status === "failed") return "failed"
    return ACTIVE_STATUSES.includes(status) ? "current" : "pending"
  })
}

const ICONS: Record<StageState, React.ReactNode> = {
  done: <CheckIcon className="size-3.5" />,
  current: <Loader2Icon className="size-3.5 animate-spin" />,
  waiting: <PauseIcon className="size-3.5" />,
  failed: <XIcon className="size-3.5" />,
  skipped: <CircleSlashIcon className="size-3.5" />,
  pending: <CircleDashedIcon className="size-3.5" />,
}

const STEP_STATUS_ICON: Record<string, React.ReactNode> = {
  completed: <CheckIcon className="size-3.5 text-emerald-400" aria-label="completed" />,
  skipped: <CircleSlashIcon className="size-3.5 text-muted-foreground" aria-label="skipped" />,
  failed: <XIcon className="size-3.5 text-red-400" aria-label="failed" />,
}

export function RunPipeline({
  steps,
  status,
  connected,
}: {
  steps: AgentStep[]
  status: RunStatus
  connected: boolean
}) {
  const states = stageStates(steps, status)
  const revisions = steps.filter((s) => s.agent === "revise").length
  const live = ACTIVE_STATUSES.includes(status) || status === "awaiting_approval"

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Agent progress
          {live && (
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-normal",
                connected ? "bg-emerald-500/10 text-emerald-300" : "bg-muted text-muted-foreground",
              )}
            >
              <RadioIcon className="size-3" aria-hidden /> {connected ? "Live" : "Connecting…"}
            </span>
          )}
        </CardTitle>
        <CardDescription>
          Research runs in parallel; production starts after you approve a concept
          {revisions ? ` · ${revisions} revision round${revisions > 1 ? "s" : ""} requested by the Critic` : ""}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <ol className="grid grid-cols-4 gap-2 md:grid-cols-8" aria-label="Workflow stages">
          {STAGES.map((stage, i) => {
            const state = states[i]!
            return (
              <li key={stage.label} className="space-y-2" aria-current={state === "current" ? "step" : undefined}>
                <div
                  className={cn(
                    "h-1 rounded-full",
                    state === "done" && "bg-primary",
                    state === "current" && "animate-pulse bg-primary/60",
                    state === "waiting" && "bg-amber-400",
                    state === "failed" && "bg-red-500",
                    (state === "pending" || state === "skipped") && "bg-muted",
                  )}
                />
                <div
                  className={cn(
                    "flex items-center gap-1.5 text-xs",
                    state === "pending" || state === "skipped" ? "text-muted-foreground" : "text-foreground",
                    state === "waiting" && "text-amber-300",
                    state === "failed" && "text-red-300",
                  )}
                >
                  {ICONS[state]}
                  <span className="truncate">{stage.label}</span>
                </div>
              </li>
            )
          })}
        </ol>

        {steps.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">Activity</p>
            <ol className="max-h-80 space-y-1 overflow-y-auto pr-1" aria-label="Agent activity log" aria-live="polite">
              {steps.map((step) => (
                <li key={step.sequence} className="flex gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-accent/50">
                  <span className="mt-0.5 shrink-0">
                    {step.agent === "revise" ? <RotateCcwIcon className="size-3.5 text-amber-300" aria-label="revision" /> : STEP_STATUS_ICON[step.status]}
                  </span>
                  <span className="w-44 shrink-0 font-medium">{agentLabel(step.agent)}</span>
                  <span className="min-w-0 flex-1 text-muted-foreground">{step.summary}</span>
                  <span className="shrink-0 tabular-nums text-xs text-muted-foreground">
                    {step.duration_ms > 0 ? formatDuration(step.duration_ms) : ""}
                  </span>
                </li>
              ))}
              {ACTIVE_STATUSES.includes(status) && (
                <li className="flex items-center gap-3 px-2 py-1.5 text-sm text-muted-foreground">
                  <Loader2Icon className="size-3.5 animate-spin" aria-hidden /> Working…
                </li>
              )}
            </ol>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
