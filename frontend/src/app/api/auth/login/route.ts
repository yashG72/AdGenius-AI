import type { NextRequest } from "next/server"

import { callBackend, forbidden, forwardError, isSameOrigin, tokenResponse } from "@/lib/auth/server"

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return forbidden()
  const backend = await callBackend("/auth/login", await request.json())
  if (!backend.ok) return forwardError(backend)
  return tokenResponse(await backend.json())
}
