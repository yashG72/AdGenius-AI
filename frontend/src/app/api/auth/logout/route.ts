import { NextResponse, type NextRequest } from "next/server"

import { REFRESH_COOKIE, callBackend, clearSession, forbidden, isSameOrigin } from "@/lib/auth/server"

/** Revoke the session server-side, then clear the cookie. */
export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return forbidden()
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value
  if (refreshToken) {
    await callBackend("/auth/logout", { refresh_token: refreshToken }).catch(() => undefined)
  }
  return clearSession(new NextResponse(null, { status: 204 }))
}
