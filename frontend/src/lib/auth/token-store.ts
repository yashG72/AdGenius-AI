/**
 * Access-token handling in the browser.
 *
 * - The short-lived ACCESS token lives only in memory (never localStorage), so a script
 *   injected into the page can't read a long-lived credential from storage.
 * - The long-lived REFRESH token lives in an httpOnly cookie that only our own
 *   /api/auth/* route handlers can see. JavaScript never touches it.
 * - Refreshing is SINGLE-FLIGHT: concurrent callers share one in-flight refresh. The
 *   backend rotates refresh tokens and treats a reused one as theft (revoking the whole
 *   session), so two parallel refreshes would log the user out.
 */

type TokenResponse = { access_token: string; expires_in: number }

let accessToken: string | null = null
let expiresAt = 0
let inFlight: Promise<string | null> | null = null

const EARLY_REFRESH_MS = 30_000 // refresh a little before expiry
export const SESSION_EXPIRED_EVENT = "adg:session-expired"

export function setAccessToken(token: TokenResponse | null): void {
  accessToken = token?.access_token ?? null
  expiresAt = token ? Date.now() + token.expires_in * 1000 : 0
}

export function clearAccessToken(): void {
  setAccessToken(null)
}

export function refreshAccessToken(): Promise<string | null> {
  inFlight ??= fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" })
    .then(async (response) => {
      if (!response.ok) {
        clearAccessToken()
        // Let the auth context know the session is gone (expired, revoked, logged out).
        window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
        return null
      }
      setAccessToken((await response.json()) as TokenResponse)
      return accessToken
    })
    .catch(() => null)
    .finally(() => {
      inFlight = null
    })
  return inFlight
}

/** A valid access token, refreshing first if it is missing or about to expire. */
export async function getAccessToken(): Promise<string | null> {
  if (accessToken && Date.now() < expiresAt - EARLY_REFRESH_MS) return accessToken
  return refreshAccessToken()
}
