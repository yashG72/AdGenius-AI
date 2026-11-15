"use client"

import {
  ActivityIcon,
  BriefcaseIcon,
  CheckCircle2Icon,
  FileTextIcon,
  GaugeIcon,
  MegaphoneIcon,
  PlusIcon,
} from "lucide-react"
import Link from "next/link"
import { useParams } from "next/navigation"

import { EmptyState } from "@/components/app/empty-state"
import { PageHeader } from "@/components/app/page-header"
import { StatCard } from "@/components/app/stat-card"
import { StatusBadge } from "@/components/app/status-badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { errorMessage } from "@/lib/api/errors"
import { formatDuration, formatPercent, formatRelative, titleCase } from "@/lib/format"
import { useDashboard } from "@/lib/queries/organizations"

function QualityRow({ label, value, ratio }: { label: string; value: string; ratio?: number | null }) {
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">{value}</span>
      </div>
      {ratio != null && <Progress value={ratio * 100} className="h-1.5" />}
    </div>
  )
}

export default function DashboardPage() {
  const { orgId } = useParams<{ orgId: string }>()
  const { data, isPending, error } = useDashboard(orgId)

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage(error)}</AlertDescription>
      </Alert>
    )
  }

  const totals = data?.totals
  const quality = data?.quality

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Your workspace at a glance: brands, knowledge, campaigns and how the agents are performing."
        actions={
          <Button asChild>
            <Link href={`/orgs/${orgId}/brands?new=1`}>
              <PlusIcon /> New brand
            </Link>
          </Button>
        }
      />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Totals">
        {isPending || !totals ? (
          Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[118px] rounded-xl" />)
        ) : (
          <>
            <StatCard label="Brands" value={totals.brands} icon={BriefcaseIcon} />
            <StatCard
              label="Knowledge base"
              value={totals.documents_indexed}
              hint={`${totals.documents} document${totals.documents === 1 ? "" : "s"} uploaded`}
              icon={FileTextIcon}
            />
            <StatCard
              label="Campaigns"
              value={totals.campaigns}
              hint={`${totals.runs} generation run${totals.runs === 1 ? "" : "s"}`}
              icon={MegaphoneIcon}
            />
            <StatCard
              label="Completed runs"
              value={totals.runs_completed}
              hint={
                totals.runs_active
                  ? `${totals.runs_active} in progress · ${totals.runs_awaiting_approval} awaiting approval`
                  : "Nothing in progress"
              }
              icon={CheckCircle2Icon}
            />
          </>
        )}
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Recent campaigns</CardTitle>
            <CardDescription>Latest generation run per campaign.</CardDescription>
          </CardHeader>
          <CardContent>
            {isPending ? (
              <Skeleton className="h-32" />
            ) : data?.recent_campaigns.length ? (
              <ul className="divide-y divide-border">
                {data.recent_campaigns.map((c) => (
                  <li key={c.id} className="flex items-center gap-3 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{c.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {c.run_count} run{c.run_count === 1 ? "" : "s"} · updated {formatRelative(c.updated_at)}
                      </p>
                    </div>
                    {c.latest_run?.overall_score != null && (
                      <span className="text-sm tabular-nums text-muted-foreground">
                        {c.latest_run.overall_score.toFixed(1)}
                      </span>
                    )}
                    {c.latest_run && <StatusBadge status={c.latest_run.status} />}
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={MegaphoneIcon}
                title="No campaigns yet"
                description="Set up a brand and its knowledge base first — campaign creation arrives in the next release."
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <GaugeIcon className="size-4 text-primary" aria-hidden /> Quality
            </CardTitle>
            <CardDescription>Critic results across evaluated runs.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {isPending || !quality ? (
              <Skeleton className="h-32" />
            ) : quality.evaluated_runs === 0 ? (
              <p className="text-sm text-muted-foreground">
                Scores appear after your first campaign is evaluated.
              </p>
            ) : (
              <>
                <QualityRow
                  label="Average score"
                  value={quality.average_score?.toFixed(1) ?? "—"}
                  ratio={quality.average_score != null ? quality.average_score / 100 : null}
                />
                <QualityRow
                  label="Approved by Critic"
                  value={formatPercent(quality.approval_rate)}
                  ratio={quality.approval_rate}
                />
                <QualityRow
                  label="Approved first time"
                  value={formatPercent(quality.first_pass_rate)}
                  ratio={quality.first_pass_rate}
                />
                <QualityRow label="Avg. revisions" value={quality.average_revisions?.toFixed(1) ?? "—"} />
                <p className="text-xs text-muted-foreground">{quality.evaluated_runs} evaluated runs</p>
              </>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ActivityIcon className="size-4 text-primary" aria-hidden /> Agent activity
            </CardTitle>
            <CardDescription>Last 30 days.</CardDescription>
          </CardHeader>
          <CardContent>
            {isPending ? (
              <Skeleton className="h-32" />
            ) : data?.agent_activity.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Agent</TableHead>
                    <TableHead className="text-right">Steps</TableHead>
                    <TableHead className="text-right">Avg. time</TableHead>
                    <TableHead className="text-right">Failures</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.agent_activity.map((a) => (
                    <TableRow key={a.agent}>
                      <TableCell>{titleCase(a.agent)}</TableCell>
                      <TableCell className="text-right tabular-nums">{a.steps}</TableCell>
                      <TableCell className="text-right tabular-nums">{formatDuration(a.average_ms)}</TableCell>
                      <TableCell className="text-right tabular-nums">{a.failures}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="text-sm text-muted-foreground">No agent runs yet.</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileTextIcon className="size-4 text-primary" aria-hidden /> Recent documents
            </CardTitle>
            <CardDescription>Newest uploads across all brands.</CardDescription>
          </CardHeader>
          <CardContent>
            {isPending ? (
              <Skeleton className="h-32" />
            ) : data?.recent_documents.length ? (
              <ul className="divide-y divide-border">
                {data.recent_documents.map((d) => (
                  <li key={d.id} className="flex items-center gap-3 py-2.5">
                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/orgs/${orgId}/brands/${d.brand_id}?tab=documents`}
                        className="block truncate text-sm hover:text-primary"
                      >
                        {d.original_filename}
                      </Link>
                      <p className="text-xs text-muted-foreground">
                        {d.brand_name} · {formatRelative(d.created_at)}
                      </p>
                    </div>
                    <StatusBadge status={d.status} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>
            )}
          </CardContent>
        </Card>
      </section>
    </>
  )
}
