"use client"

import { Loader2Icon } from "lucide-react"
import { usePathname, useRouter } from "next/navigation"
import { useEffect } from "react"

import { useAuth } from "@/lib/auth/auth-context"

/** Client-side guard: signed-out visitors are sent to /login and brought back afterwards. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status, user } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (status === "anonymous") router.replace(`/login?next=${encodeURIComponent(pathname)}`)
  }, [status, pathname, router])

  if (status !== "authenticated" || !user) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Loader2Icon className="size-6 animate-spin text-muted-foreground" aria-label="Loading" />
      </div>
    )
  }
  return <>{children}</>
}
