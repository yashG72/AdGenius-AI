import { Loader2Icon } from "lucide-react"
import { Suspense } from "react"

import { RequireAuth } from "@/components/auth/require-auth"

function FullPageSpinner() {
  return (
    <div className="grid min-h-screen place-items-center">
      <Loader2Icon className="size-6 animate-spin text-muted-foreground" aria-label="Loading" />
    </div>
  )
}

export default function OrgsLayout({ children }: { children: React.ReactNode }) {
  // Everything under /orgs reads the URL (pathname, params) in client components.
  // Next 16 requires that to happen inside a Suspense boundary so the static shell can
  // be prerendered and the URL-dependent part streamed in.
  return (
    <Suspense fallback={<FullPageSpinner />}>
      <RequireAuth>{children}</RequireAuth>
    </Suspense>
  )
}
