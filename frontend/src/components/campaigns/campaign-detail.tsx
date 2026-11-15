"use client"

import { ArrowLeftIcon, HistoryIcon, PencilIcon, SparklesIcon } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { toast } from "sonner"

import { EmptyState } from "@/components/app/empty-state"
import { PageHeader } from "@/components/app/page-header"
import { StatusBadge } from "@/components/app/status-badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { errorMessage } from "@/lib/api/errors"
import type { BriefFields } from "@/lib/api/types"
import { ACTIVE_STATUSES } from "@/lib/api/types"
import { formatDateTime, formatRelative, titleCase } from "@/lib/format"
import { useBrand } from "@/lib/queries/brands"
import { useCampaign, useRuns, useStartRun } from "@/lib/queries/campaigns"

function BriefRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === "" || value == null) return null
  return (
    <div className="space-y-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm whitespace-pre-wrap">{value}</dd>
    </div>
  )
}

export function CampaignDetail({ orgId, campaignId }: { orgId: string; campaignId: string }) {
  const router = useRouter()
  const campaign = useCampaign(campaignId)
  const runs = useRuns(campaignId)
  const brand = useBrand(campaign.data?.brand_id ?? "")
  const { generate } = useStartRun(orgId, campaignId)
  const active = runs.data?.find((r) => ACTIVE_STATUSES.includes(r.status))

  if (campaign.error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage(campaign.error)}</AlertDescription>
      </Alert>
    )
  }
  if (campaign.isPending) return <Skeleton className="h-96 rounded-xl" />
  const c = campaign.data
  const brief = c.brief as BriefFields

  const onGenerate = () =>
    generate.mutate(undefined, {
      onSuccess: (run) => router.push(`/orgs/${orgId}/campaigns/${c.id}/runs/${run.id}`),
      onError: (e) => toast.error(errorMessage(e)),
    })

  return (
    <>
      <Link href={`/orgs/${orgId}/campaigns`} className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeftIcon className="size-4" /> All campaigns
      </Link>
      <PageHeader
        title={c.name}
        description={`${brand.data?.name ?? ""} · ${titleCase(brief.platform ?? "")} · ${brief.video_format} · ${brief.duration_seconds}s`}
        actions={
          <>
            <Button variant="outline" asChild>
              <Link href={`/orgs/${orgId}/campaigns/${c.id}/edit`}>
                <PencilIcon /> Edit brief
              </Link>
            </Button>
            <Button onClick={onGenerate} disabled={generate.isPending || !!active} title={active ? "A run is already in progress" : undefined}>
              <SparklesIcon /> {c.run_count ? "Generate new version" : "Generate"}
            </Button>
          </>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <HistoryIcon className="size-4 text-primary" aria-hidden /> Campaign history
            </CardTitle>
            <CardDescription>Every generation is a separate version; nothing is overwritten.</CardDescription>
          </CardHeader>
          <CardContent>
            {runs.isPending ? (
              <Skeleton className="h-32" />
            ) : !runs.data?.length ? (
              <EmptyState icon={SparklesIcon} title="Not generated yet" description="Start the agents to create the first version." />
            ) : (
              <ol className="relative space-y-1 border-l border-border pl-5">
                {runs.data.map((run) => (
                  <li key={run.id}>
                    <span className="absolute -left-[5px] mt-4 size-2.5 rounded-full border-2 border-background bg-muted-foreground" aria-hidden />
                    <Link
                      href={`/orgs/${orgId}/campaigns/${c.id}/runs/${run.id}`}
                      className="flex flex-wrap items-center gap-3 rounded-lg px-3 py-3 transition-colors hover:bg-accent"
                    >
                      <span className="font-medium">Version {run.version}</span>
                      <StatusBadge status={run.status} />
                      {run.overall_score != null && (
                        <span className="text-sm tabular-nums text-muted-foreground">score {run.overall_score.toFixed(1)}</span>
                      )}
                      {run.parent_run_id && <span className="text-xs text-muted-foreground">regenerated</span>}
                      <span className="ml-auto text-xs text-muted-foreground" title={formatDateTime(run.created_at)}>
                        {formatRelative(run.created_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Brief</CardTitle>
            <CardDescription>Used by future runs. Each run keeps a snapshot of the brief it started with.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="space-y-3">
              <BriefRow label="Objective" value={brief.objective} />
              <BriefRow label="Marketing objective" value={brief.marketing_objective} />
              <BriefRow label="Product" value={brief.product_description} />
              <BriefRow label="Target audience" value={brief.target_audience} />
              <BriefRow label="Tone" value={brief.tone} />
              <BriefRow label="Language" value={brief.language} />
              <BriefRow label="Concepts" value={brief.num_concepts} />
              <BriefRow label="Budget" value={brief.budget} />
              <BriefRow label="Requirements" value={brief.additional_requirements} />
              <BriefRow label="Competitor research" value={brief.competitor_research ? brief.competitor_focus || "Yes" : "Off"} />
            </dl>
          </CardContent>
        </Card>
      </div>
    </>
  )
}
