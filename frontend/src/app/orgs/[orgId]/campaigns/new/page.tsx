import type { Metadata } from "next"
import { Suspense } from "react"

import { PageHeader } from "@/components/app/page-header"
import { CampaignWizard } from "@/components/campaigns/campaign-wizard"

export const metadata: Metadata = { title: "New campaign" }

async function Wizard({ params, searchParams }: PageProps<"/orgs/[orgId]/campaigns/new">) {
  const { orgId } = await params
  const { brand } = await searchParams
  return <CampaignWizard orgId={orgId} initialBrandId={typeof brand === "string" ? brand : undefined} />
}

export default function NewCampaignPage(props: PageProps<"/orgs/[orgId]/campaigns/new">) {
  return (
    <>
      <PageHeader
        title="New campaign"
        description="Write the brief. Six agents then research, ideate, script, storyboard and critique it."
      />
      <Suspense>
        <Wizard {...props} />
      </Suspense>
    </>
  )
}
