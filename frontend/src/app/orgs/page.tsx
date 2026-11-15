import type { Metadata } from "next"
import { Suspense } from "react"

import { OrgPicker } from "@/components/app/org-picker"

export const metadata: Metadata = { title: "Workspaces" }

export default function OrganizationsPage() {
  // OrgPicker reads ?choose via useSearchParams, which needs a Suspense boundary.
  return (
    <Suspense>
      <OrgPicker />
    </Suspense>
  )
}
