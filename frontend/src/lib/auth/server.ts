/**
 * Server-side helpers for the /api/auth/* route handlers ("backend for frontend").
 *
 * These handlers are the ONLY code that ever sees the refresh token. They call the
 * FastAPI auth endpoints, keep the refresh token in an httpOnly cookie, and hand only
 * the short-lived access token to the browser.
 */

import { NextResponse, type NextRequest } from "next/server"

import { SERVER_API_URL } from "@/lib/config"

export const REFRESH_COOKIE = "adg_refresh"

type TokenPair = { access_token: string; refresh_token: string; expires_in: number }

/** Reject cross-site requests (defence in depth on top of SameSite=Lax cookies). */
export function isSameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin")
  return !origin || origin === request.nextUrl.origin
}

/**
 * The browser's IP as this server saw it. The API rate-limits sign-ins per client IP;
 * without this every user would share the Next.js server's address. The API only
 * believes X-Forwarded-For from its trusted proxies (TRUSTED_PROXIES), i.e. this server.
 */
function forwardedFor(request: NextRequest): string | undefined {
  return request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip") ?? undefined
}

export async function callBackend(path: string, body: unknown, request: NextRequest): Promise<Response> {
  const forwarded = forwardedFor(request)
  return fetch(`${SERVER_API_URL}/api/v1${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(forwarded ? { "X-Forwarded-For": forwarded } : {}) },
    body: JSON.stringify(body),
    cache: "no-store",
  })
}

/** Respond with the access token only; store the refresh token in an httpOnly cookie. */
export function tokenResponse(pair: TokenPair): NextResponse {
  const response = NextResponse.json({
    access_token: pair.access_token,
    expires_in: pair.expires_in,
  })
  response.cookies.set(REFRESH_COOKIE, pair.refresh_token, {
    httpOnly: true, // invisible to JavaScript
    secure: process.env.NODE_ENV === "production", // HTTPS-only in production
    sameSite: "lax", // not sent on cross-site POSTs
    path: "/api/auth", // only sent to these route handlers, not to every page
    maxAge: 60 * 60 * 24 * 30,
  })
  return response
}

export function clearSession(response: NextResponse): NextResponse {
  response.cookies.set(REFRESH_COOKIE, "", { path: "/api/auth", maxAge: 0 })
  return response
}

/** Pass the backend's error status + envelope (and Retry-After on 429) straight through. */
export async function forwardError(backend: Response): Promise<NextResponse> {
  const body = await backend.json().catch(() => ({ error: { message: "Auth service error" } }))
  const retryAfter = backend.headers.get("retry-after")
  return NextResponse.json(body, {
    status: backend.status,
    headers: retryAfter ? { "Retry-After": retryAfter } : undefined,
  })
}

export const forbidden = () =>
  NextResponse.json({ error: { code: "forbidden", message: "Cross-site request" } }, { status: 403 })
