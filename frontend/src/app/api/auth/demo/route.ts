import type { NextRequest } from "next/server"

import { callBackend, forbidden, forwardError, isSameOrigin, tokenResponse } from "@/lib/auth/server"

/** "Try the demo": sign into the shared read-only demo workspace (no credentials). */
export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return forbidden()
  const backend = await callBackend("/auth/demo", {}, request)
  if (!backend.ok) return forwardError(backend)
  return tokenResponse(await backend.json())
}
