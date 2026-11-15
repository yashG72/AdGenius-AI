import type { Metadata } from "next"
import { Suspense } from "react"

import { RunWorkspace } from "@/components/runs/run-workspace"

export const metadata: Metadata = { title: "Campaign run" }

export default async function RunPage({ params }: PageProps<"/orgs/[orgId]/campaigns/[campaignId]/runs/[runId]">) {
  const { orgId, campaignId, runId } = await params
  return (
    <Suspense>
      <RunWorkspace orgId={orgId} campaignId={campaignId} runId={runId} />
    </Suspense>
  )
}
