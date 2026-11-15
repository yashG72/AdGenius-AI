import { NextResponse, type NextRequest } from "next/server"

import {
  REFRESH_COOKIE,
  callBackend,
  clearSession,
  forbidden,
  isSameOrigin,
  tokenResponse,
} from "@/lib/auth/server"

/** Exchange the httpOnly refresh cookie for a new access token (rotating the cookie). */
export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return forbidden()
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value
  if (!refreshToken) {
    return NextResponse.json({ error: { code: "not_authenticated" } }, { status: 401 })
  }
  const backend = await callBackend("/auth/refresh", { refresh_token: refreshToken })
  if (!backend.ok) {
    // Expired, revoked or reused: the session is over, drop the cookie.
    return clearSession(NextResponse.json(await backend.json(), { status: backend.status }))
  }
  return tokenResponse(await backend.json())
}
