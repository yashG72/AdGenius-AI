/** Remembers the last workspace so returning users land straight in it. */
const LAST_ORG_KEY = "adg:last-org"

export function rememberOrg(orgId: string): void {
  try {
    localStorage.setItem(LAST_ORG_KEY, orgId)
  } catch {
    // storage unavailable (private mode): nothing to remember
  }
}

export function lastOrg(): string | null {
  try {
    return localStorage.getItem(LAST_ORG_KEY)
  } catch {
    return null
  }
}
