"use client"

import { MegaphoneIcon, PlusIcon } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { EmptyState } from "@/components/app/empty-state"
import { PageHeader } from "@/components/app/page-header"
import { StatusBadge } from "@/components/app/status-badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { errorMessage } from "@/lib/api/errors"
import { formatRelative, titleCase } from "@/lib/format"
import { useBrands } from "@/lib/queries/brands"
import { useCampaigns } from "@/lib/queries/campaigns"

const ALL = "all"

export function CampaignList({ orgId }: { orgId: string }) {
  const [brandId, setBrandId] = useState(ALL)
  const brands = useBrands(orgId)
  const { data, isPending, error } = useCampaigns(orgId, brandId === ALL ? undefined : brandId)
  const brandName = (id: string) => brands.data?.items.find((b) => b.id === id)?.name ?? "—"

  return (
    <>
      <PageHeader
        title="Campaigns"
        description="Every campaign and its latest generation run. Open one to follow the agents live or review results."
        actions={
          <Button asChild>
            <Link href={`/orgs/${orgId}/campaigns/new`}>
              <PlusIcon /> New campaign
            </Link>
          </Button>
        }
      />

      <div className="flex items-center gap-3">
        <Select value={brandId} onValueChange={setBrandId}>
          <SelectTrigger className="w-56" aria-label="Filter by brand">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All brands</SelectItem>
            {brands.data?.items.map((b) => (
              <SelectItem key={b.id} value={b.id}>
                {b.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(error)}</AlertDescription>
        </Alert>
      ) : isPending ? (
        <Skeleton className="h-48 rounded-xl" />
      ) : data.items.length === 0 ? (
        <EmptyState
          icon={MegaphoneIcon}
          title="No campaigns yet"
          description="Write a brief and the agents will research, ideate, script and storyboard it for you."
          action={
            <Button asChild>
              <Link href={`/orgs/${orgId}/campaigns/new`}>
                <PlusIcon /> New campaign
              </Link>
            </Button>
          }
        />
      ) : (
        <Card className="py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Campaign</TableHead>
                <TableHead>Brand</TableHead>
                <TableHead>Latest run</TableHead>
                <TableHead className="text-right">Score</TableHead>
                <TableHead className="text-right">Runs</TableHead>
                <TableHead className="pr-4">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((c) => {
                const brief = c.brief as { platform?: string; duration_seconds?: number }
                return (
                  <TableRow key={c.id} className="cursor-pointer">
                    <TableCell className="pl-4">
                      <Link href={`/orgs/${orgId}/campaigns/${c.id}`} className="font-medium hover:text-primary">
                        {c.name}
                      </Link>
                      <p className="text-xs text-muted-foreground">
                        {titleCase(brief.platform ?? "")} · {brief.duration_seconds}s
                      </p>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{brandName(c.brand_id)}</TableCell>
                    <TableCell>
                      {c.latest_run ? <StatusBadge status={c.latest_run.status} /> : <span className="text-sm text-muted-foreground">Not generated</span>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {c.latest_run?.overall_score != null ? c.latest_run.overall_score.toFixed(1) : "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{c.run_count}</TableCell>
                    <TableCell className="pr-4 text-sm text-muted-foreground">{formatRelative(c.updated_at)}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Card>
      )}
    </>
  )
}
