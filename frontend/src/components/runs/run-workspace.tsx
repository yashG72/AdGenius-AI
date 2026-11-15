"use client"

import { ArrowLeftIcon, DownloadIcon, RefreshCwIcon, RotateCcwIcon } from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { StatusBadge } from "@/components/app/status-badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useRunEvents } from "@/hooks/use-run-events"
import { errorMessage } from "@/lib/api/errors"
import type { OutputType } from "@/lib/api/types"
import { TERMINAL_STATUSES } from "@/lib/api/types"
import { formatDateTime } from "@/lib/format"
import { downloadRunPdf, useCampaign, useRun, useStartRun } from "@/lib/queries/campaigns"

import { ConceptApproval } from "./concept-approval"
import { ConceptsView } from "./concepts-view"
import { EvaluationView } from "./evaluation-view"
import { ResearchView } from "./research-view"
import { RunPipeline } from "./run-pipeline"
import { ScriptEditor } from "./script-editor"
import { StoryboardEditor } from "./storyboard-editor"

const TABS: { value: string; label: string; needs: OutputType }[] = [
  { value: "evaluation", label: "Evaluation", needs: "evaluation" },
  { value: "script", label: "Script", needs: "script" },
  { value: "storyboard", label: "Storyboard", needs: "storyboard" },
  { value: "concepts", label: "Concepts", needs: "concepts" },
  { value: "research", label: "Research", needs: "brand_research" },
]

export function RunWorkspace({ orgId, campaignId, runId }: { orgId: string; campaignId: string; runId: string }) {
  const router = useRouter()
  const pathname = usePathname()
  const requestedTab = useSearchParams().get("tab")
  const run = useRun(runId)
  const campaign = useCampaign(campaignId)
  const { regenerate, retry } = useStartRun(orgId, campaignId)
  const [downloading, setDownloading] = useState(false)

  const status = run.data?.status
  const finished = !!status && TERMINAL_STATUSES.includes(status)
  const { connected } = useRunEvents(runId, !!status && !finished)

  if (run.error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage(run.error)}</AlertDescription>
      </Alert>
    )
  }
  if (run.isPending) return <Skeleton className="h-96 rounded-xl" />
  const r = run.data

  const available = new Set(r.outputs.map((o) => o.output_type))
  // While a decision is pending, the approval panel already shows the concepts.
  const tabs = TABS.filter(
    (t) => available.has(t.needs) && !(t.value === "concepts" && r.pending_approval),
  )
  const tab = tabs.find((t) => t.value === requestedTab)?.value ?? tabs[0]?.value
  const editable = r.status === "completed" || r.status === "needs_review"

  const onDownload = async () => {
    setDownloading(true)
    try {
      await downloadRunPdf(runId)
    } catch (e) {
      toast.error(errorMessage(e))
    } finally {
      setDownloading(false)
    }
  }
  const onRegenerate = () =>
    regenerate.mutate(runId, {
      onSuccess: (next) => {
        toast.success(`Version ${next.version} started`)
        router.push(`/orgs/${orgId}/campaigns/${campaignId}/runs/${next.id}`)
      },
      onError: (e) => toast.error(errorMessage(e)),
    })
  const onRetry = () =>
    retry.mutate(runId, {
      onSuccess: () => toast.success("Retrying from the last checkpoint"),
      onError: (e) => toast.error(errorMessage(e)),
    })

  return (
    <>
      <Link
        href={`/orgs/${orgId}/campaigns/${campaignId}`}
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeftIcon className="size-4" /> {campaign.data?.name ?? "Campaign"}
      </Link>

      <div className="flex flex-col gap-4 border-b border-border/60 pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-heading text-2xl font-semibold tracking-tight">
              {campaign.data?.name} <span className="text-muted-foreground">· v{r.version}</span>
            </h1>
            <StatusBadge status={r.status} />
            {r.overall_score != null && (
              <span className="rounded-full bg-muted px-2.5 py-0.5 text-sm tabular-nums">{r.overall_score.toFixed(1)}/100</span>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            Started {formatDateTime(r.started_at ?? r.created_at)}
            {r.finished_at && ` · finished ${formatDateTime(r.finished_at)}`}
            {/* attempts counts every work segment (start, resume); only meaningful after a failure */}
            {r.status === "failed" && r.attempts > 1 && ` · ${r.attempts} attempts`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {r.status === "failed" && (
            <Button variant="outline" onClick={onRetry} disabled={retry.isPending}>
              <RotateCcwIcon /> Retry
            </Button>
          )}
          {finished && (
            <Button variant="outline" onClick={onRegenerate} disabled={regenerate.isPending}>
              <RefreshCwIcon /> Regenerate
            </Button>
          )}
          {available.has("final_campaign") && (
            <Button onClick={onDownload} disabled={downloading}>
              <DownloadIcon /> {downloading ? "Preparing…" : "Download PDF"}
            </Button>
          )}
        </div>
      </div>

      {r.status === "failed" && (
        <Alert variant="destructive">
          <AlertTitle>This run failed</AlertTitle>
          <AlertDescription>
            {r.error_message ?? "Unknown error."} Retry continues from the last saved step — finished agents are not re-run.
          </AlertDescription>
        </Alert>
      )}
      {r.status === "needs_review" && (
        <Alert>
          <AlertTitle>Needs your review</AlertTitle>
          <AlertDescription>
            The Critic&apos;s score stayed below the pass mark after the automatic revisions. The result is kept — check the
            Evaluation tab, then edit the script or storyboard, or regenerate.
          </AlertDescription>
        </Alert>
      )}

      {r.pending_approval && <ConceptApproval runId={runId} approval={r.pending_approval} />}

      <RunPipeline steps={r.agent_runs} status={r.status} connected={connected} />

      {tab && (
        <Tabs value={tab} onValueChange={(v) => router.replace(`${pathname}?tab=${v}`, { scroll: false })}>
          <TabsList>
            {tabs.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="evaluation" className="mt-6">
            <EvaluationView runId={runId} />
          </TabsContent>
          <TabsContent value="script" className="mt-6">
            <ScriptEditor runId={runId} editable={editable} />
          </TabsContent>
          <TabsContent value="storyboard" className="mt-6">
            <StoryboardEditor runId={runId} editable={editable} />
          </TabsContent>
          <TabsContent value="concepts" className="mt-6">
            <ConceptsView runId={runId} />
          </TabsContent>
          <TabsContent value="research" className="mt-6">
            <ResearchView runId={runId} />
          </TabsContent>
        </Tabs>
      )}
    </>
  )
}
