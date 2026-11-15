import type { Metadata } from "next"
import { Suspense } from "react"

import { BrandDetail } from "@/components/brands/brand-detail"

export const metadata: Metadata = { title: "Brand" }

export default async function BrandPage({ params }: PageProps<"/orgs/[orgId]/brands/[brandId]">) {
  const { orgId, brandId } = await params
  return (
    <Suspense>
      <BrandDetail orgId={orgId} brandId={brandId} />
    </Suspense>
  )
}
