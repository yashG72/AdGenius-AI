import type { Metadata } from "next"

import { CampaignDetail } from "@/components/campaigns/campaign-detail"

export const metadata: Metadata = { title: "Campaign" }

export default async function CampaignPage({ params }: PageProps<"/orgs/[orgId]/campaigns/[campaignId]">) {
  const { orgId, campaignId } = await params
  return <CampaignDetail orgId={orgId} campaignId={campaignId} />
}
