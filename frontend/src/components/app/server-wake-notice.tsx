"use client"

import { LoaderCircleIcon } from "lucide-react"
import { useEffect, useState } from "react"

import { API_URL } from "@/lib/config"

const SLOW_AFTER_MS = 2500 // a warm server answers well within this
const RETRY_EVERY_MS = 3000

/**
 * Free hosting puts the API to sleep when idle, and waking it takes up to a minute.
 * This pings the API's liveness endpoint as soon as the sign-in page opens (which also
 * starts the wake-up early) and, only if it's slow, explains the wait instead of
 * letting the first sign-in attempt look broken. Renders nothing when the API is warm.
 */
export function ServerWakeNotice() {
  const [state, setState] = useState<"checking" | "waking" | "ready">("checking")

  useEffect(() => {
    let cancelled = false
    const slow = setTimeout(() => !cancelled && setState((s) => (s === "checking" ? "waking" : s)), SLOW_AFTER_MS)

    async function ping() {
      while (!cancelled) {
        try {
          const response = await fetch(`${API_URL}/api/v1/health`, { cache: "no-store" })
          if (response.ok) {
            if (!cancelled) setState("ready")
            return
          }
        } catch {
          // still starting (connection refused / gateway error): try again
        }
        await new Promise((resolve) => setTimeout(resolve, RETRY_EVERY_MS))
      }
    }
    void ping()
    return () => {
      cancelled = true
      clearTimeout(slow)
    }
  }, [])

  if (state !== "waking") return null
  return (
    <div
      role="status"
      className="flex items-start gap-3 rounded-lg border border-primary/30 bg-primary/10 px-4 py-3 text-sm"
    >
      <LoaderCircleIcon className="mt-0.5 size-4 shrink-0 animate-spin text-primary" aria-hidden />
      <p>
        <span className="font-medium">Waking up the demo server…</span>{" "}
        <span className="text-muted-foreground">
          It runs on a free plan that sleeps when idle, so the first visit can take up to a minute.
        </span>
      </p>
    </div>
  )
}
