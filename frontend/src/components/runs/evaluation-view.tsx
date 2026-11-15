"use client"

import {
  AlertCircleIcon,
  ArrowRightIcon,
  CheckCircle2Icon,
  InfoIcon,
  OctagonXIcon,
  ThumbsUpIcon,
  TriangleAlertIcon,
} from "lucide-react"

import { BarChart } from "@/components/charts/bar-chart"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import type { Issue, Severity } from "@/lib/api/types"
import { formatDuration, titleCase } from "@/lib/format"
import { useEvaluationSummary } from "@/lib/queries/campaigns"
import { cn } from "@/lib/utils"

import { agentLabel } from "./run-pipeline"

// Status palette: reserved for severity, always with an icon + label (never color alone).
const SEVERITY: Record<Severity, { label: string; icon: typeof InfoIcon; className: string }> = {
  critical: { label: "Critical", icon: OctagonXIcon, className: "text-red-300 border-red-500/30 bg-red-500/10" },
  high: { label: "High", icon: TriangleAlertIcon, className: "text-orange-300 border-orange-500/30 bg-orange-500/10" },
  medium: { label: "Medium", icon: AlertCircleIcon, className: "text-amber-300 border-amber-500/30 bg-amber-500/10" },
  low: { label: "Low", icon: InfoIcon, className: "text-sky-300 border-sky-500/30 bg-sky-500/10" },
}
const ORDER: Severity[] = ["critical", "high", "medium", "low"]

function SeverityBadge({ severity }: { severity: Severity }) {
  const { label, icon: Icon, className } = SEVERITY[severity]
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", className)}>
      <Icon className="size-3" aria-hidden /> {label}
    </span>
  )
}

export function EvaluationView({ runId }: { runId: string }) {
  const { data, isPending } = useEvaluationSummary(runId, true)
  if (isPending) return <Skeleton className="h-96 rounded-xl" />
  if (!data) return <p className="text-sm text-muted-foreground">The Critic hasn&apos;t evaluated this run yet.</p>

  const issues = [...(data.issues as Issue[])].sort((a, b) => ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity))
  const dimensionRows = Object.entries(data.scores)
    .map(([key, value]) => ({ label: titleCase(key), value }))
    .sort((a, b) => b.value - a.value)
  const timingRows = data.agent_timings
    .filter((t) => t.total_ms >= 50) // skip instant bookkeeping steps (merge, approval, finalize)
    .map((t) => ({ label: `${agentLabel(t.agent)}${t.runs > 1 ? ` ×${t.runs}` : ""}`, value: t.total_ms }))

  return (
    <div className="space-y-6">
      {/* Headline: a hero number, not a chart */}
      <Card>
        <CardContent className="flex flex-wrap items-center gap-x-10 gap-y-6">
          <div>
            <p className="text-sm text-muted-foreground">Overall quality</p>
            <p className="font-heading text-5xl font-semibold tabular-nums tracking-tight">
              {data.overall_score.toFixed(1)}
              <span className="text-2xl text-muted-foreground">/100</span>
            </p>
          </div>
          <div className="space-y-2">
            {data.passed ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-sm text-emerald-300">
                <CheckCircle2Icon className="size-4" aria-hidden /> Approved by the Critic
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-sm text-amber-300">
                <TriangleAlertIcon className="size-4" aria-hidden /> Needs human review
              </span>
            )}
            <p className="text-sm text-muted-foreground">
              Pass mark {data.threshold} · {data.iterations.length} critique{data.iterations.length > 1 ? "s" : ""}
              {data.score_change !== 0 && ` · ${data.score_change > 0 ? "+" : ""}${data.score_change.toFixed(1)} from revisions`}
            </p>
          </div>
          {/* Score per critique: at most 3 numbers, so a step strip instead of a line chart */}
          {data.iterations.length > 1 && (
            <ol className="flex flex-wrap items-center gap-2" aria-label="Score per critique">
              {data.iterations.map((it, i) => (
                <li key={it.iteration} className="flex items-center gap-2">
                  {i > 0 && <ArrowRightIcon className="size-4 text-muted-foreground" aria-hidden />}
                  <span className="rounded-lg border border-border px-3 py-1.5 text-center">
                    <span className="block text-xs text-muted-foreground">Critique {it.iteration}</span>
                    <span className="block font-medium tabular-nums">
                      {it.overall_score.toFixed(1)} {it.passed ? "✓" : "✗"}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Scores by dimension</CardTitle>
            <CardDescription>Latest critique, 0–100. Dashed line = pass mark.</CardDescription>
          </CardHeader>
          <CardContent>
            <BarChart
              title="Dimension"
              unitLabel="out of 100"
              rows={dimensionRows}
              max={100}
              threshold={data.threshold}
              thresholdLabel={`pass ${data.threshold}`}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Issues</CardTitle>
            <CardDescription>
              {issues.length
                ? ORDER.filter((s) => data.issues_by_severity[s]).map((s) => `${data.issues_by_severity[s]} ${s}`).join(" · ")
                : "No open issues."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {issues.map((issue, i) => (
                <li key={i} className="space-y-1.5 rounded-lg border border-border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={issue.severity} />
                    <span className="text-xs text-muted-foreground">
                      {titleCase(issue.dimension)} · fix in {issue.target}
                    </span>
                  </div>
                  <p className="text-sm">{issue.description}</p>
                  <p className="text-sm text-muted-foreground">→ {issue.suggestion}</p>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ThumbsUpIcon className="size-4 text-primary" aria-hidden /> Strengths & summary
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <ul className="list-disc space-y-1 pl-5">
              {data.strengths.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
            <p className="text-muted-foreground">{data.overall_feedback}</p>
            {data.revision_history.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Revision history</p>
                <ol className="space-y-1">
                  {data.revision_history.map((r) => (
                    <li key={r.iteration}>
                      Round {r.iteration}: scored {r.overall_score.toFixed(1)}, {r.issue_count} issue
                      {r.issue_count === 1 ? "" : "s"} → sent to {agentLabel(r.routed_to)}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Time per agent</CardTitle>
            <CardDescription>Total {formatDuration(data.total_agent_ms)} of agent work.</CardDescription>
          </CardHeader>
          <CardContent>
            <BarChart
              title="Agent"
              unitLabel="time"
              rows={timingRows}
              max={Math.max(...timingRows.map((r) => r.value), 1)}
              format={formatDuration}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
