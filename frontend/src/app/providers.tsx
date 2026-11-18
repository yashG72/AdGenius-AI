"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"

import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { ApiError } from "@/lib/api/errors"
import { AuthProvider } from "@/lib/auth/auth-context"

let browserQueryClient: QueryClient | undefined

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Retry network hiccups, but never "you can't see this" answers - nor 429:
        // retrying a rate-limited call only extends the wait.
        retry: (failures, error) =>
          !(error instanceof ApiError && [400, 401, 403, 404, 409, 413, 422, 429].includes(error.status)) &&
          failures < 2,
      },
    },
  })
}

function getQueryClient() {
  // Keep server renders isolated; reuse one client in the browser.
  if (typeof window === "undefined") return makeQueryClient()
  browserQueryClient ??= makeQueryClient()
  return browserQueryClient
}

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={getQueryClient()}>
      <TooltipProvider>
        <AuthProvider>{children}</AuthProvider>
        <Toaster richColors position="bottom-right" />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
