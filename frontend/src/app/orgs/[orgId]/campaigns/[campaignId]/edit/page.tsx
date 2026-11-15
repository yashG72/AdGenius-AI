"use client"

import { useParams } from "next/navigation"

import { PageHeader } from "@/components/app/page-header"
import { CampaignWizard } from "@/components/campaigns/campaign-wizard"
import { Skeleton } from "@/components/ui/skeleton"
import { useCampaign } from "@/lib/queries/campaigns"

export default function EditCampaignPage() {
  const { orgId, campaignId } = useParams<{ orgId: string; campaignId: string }>()
  const campaign = useCampaign(campaignId)
  return (
    <>
      <PageHeader title="Edit brief" description="Changes apply to future runs; earlier versions keep the brief they used." />
      {campaign.data ? <CampaignWizard orgId={orgId} campaign={campaign.data} /> : <Skeleton className="h-96 rounded-xl" />}
    </>
  )
}
