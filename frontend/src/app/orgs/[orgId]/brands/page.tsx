import type { Metadata } from "next"
import { Suspense } from "react"

import { BrandList } from "@/components/brands/brand-list"

export const metadata: Metadata = { title: "Brands" }

export default async function BrandsPage({ params }: PageProps<"/orgs/[orgId]/brands">) {
  const { orgId } = await params // Next 16: params is a Promise
  return (
    <Suspense>
      <BrandList orgId={orgId} />
    </Suspense>
  )
}
