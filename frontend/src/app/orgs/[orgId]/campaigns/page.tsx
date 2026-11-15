import type { Metadata } from "next"

import { CampaignList } from "@/components/campaigns/campaign-list"

export const metadata: Metadata = { title: "Campaigns" }

export default async function CampaignsPage({ params }: PageProps<"/orgs/[orgId]/campaigns">) {
  const { orgId } = await params
  return <CampaignList orgId={orgId} />
}
