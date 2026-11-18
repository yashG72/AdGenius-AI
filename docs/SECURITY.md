# Security

This document describes how AdGenius AI protects accounts, tenant data and paid AI
resources, which limits apply, and which gaps are known. It was written during the phase 12
security review. Update it whenever a control changes.

## Threat model in one paragraph

Several organizations (tenants) share one deployment. The main risks:

- **Account takeover:** credential stuffing, token theft.
- **Cross-tenant data access:** reading another organization's brands, documents or
  campaigns.
- **Prompt injection:** through uploaded documents and web pages fed to the LLM.
- **Cost abuse:** each campaign run spends roughly ten LLM calls and several paid web
  searches.
- **Resource exhaustion:** huge request bodies, upload floods.

## Controls

### Authentication and sessions

| Control | Where |
|---|---|
| Argon2id password hashing, transparent rehash on parameter upgrades | `app/core/security.py`, `auth_service.authenticate` |
| Dummy hash check for unknown emails (equal timing, no user enumeration) | `auth_service.authenticate` |
| Passwords 8–128 characters (the upper bound stops oversized-hash CPU abuse) | `app/schemas/auth.py` |
| Short-lived JWT access tokens (15 min, HS256 only, `alg=none` rejected) | `app/core/security.py` |
| Opaque refresh tokens stored only as SHA-256 hashes; single use; **reuse revokes the whole session family** | `auth_service.rotate_refresh_token` |
| Password change signs out every session | `auth_service.change_password` |
| Web app: refresh token lives in an `httpOnly`, `SameSite=Lax` cookie scoped to `/api/auth`; JavaScript only ever sees the access token (kept in memory) | `frontend/src/lib/auth/server.ts` |
| Same-origin check on the cookie-handling route handlers | `isSameOrigin` |
| Expired token families are purged daily (consumed tokens of live families are kept, because reuse detection needs them) | `maintenance.purge_refresh_tokens` (Celery beat) |

### Brute-force and cost protection (rate limits)

Fixed-window counters live in Redis, incremented atomically by a Lua script
(`app/core/rate_limit.py`). The policies are in `app/api/rate_limits.py`:

| Limit | Subject | Budget |
|---|---|---|
| Failed sign-ins | **account (email)** | 5 per 15 min, then locked for the rest of the window |
| Sign-in attempts | client IP | 30 per 15 min |
| Registration | client IP | 10 per hour |
| Token refresh | client IP | 120 per 15 min |
| Password change | user | 5 per 15 min |
| Knowledge search | user | 60 per min |
| Knowledge Q&A (LLM) | user | 20 per min |
| Competitor web research | user | 10 per hour |
| Campaign runs (generate / regenerate / retry) | user | 20 per hour |
| Document uploads | user | 60 per hour |

- A blocked call gets `429 rate_limited` with a `Retry-After` header. The frontend never
  retries a 429 automatically.
- The account lockout gives the same answer whether or not the email exists.
- **Client IP:** `X-Forwarded-For` is trusted only when the direct peer is listed in
  `TRUSTED_PROXIES` (default: localhost, i.e. the Next.js server). Configure this to the
  load balancer's addresses in deployment.
- **Redis down:** limits **fail open** and a warning is logged. This is deliberate:
  locking everyone out is worse here. Alert on that warning in production.
- `RATE_LIMIT_ENABLED=false` switches limits off (local experiments only).

### Tenant isolation and authorization

- Every organization-scoped query filters by the caller's memberships. A resource in
  another organization returns **404, not 403**, so its existence never leaks.
- Roles: owner > admin > member. Membership is checked in `require_membership`, and the
  member-management rules prevent removing or demoting the last owner.
- Qdrant points carry `organization_id` (an `is_tenant` index), and every vector search
  filters by organization and brand. Search results are re-checked against live database
  rows, so deleted documents never surface.
- Users deactivated after a token was issued are rejected on every request (the DB is
  re-checked).

### Input handling

- **Request bodies:** JSON over 1 MB and multipart over the upload limit + 1 MB are
  rejected with `413` before parsing. The size is checked from the declared
  `Content-Length` and also counted while streaming (`BodySizeLimitMiddleware`).
- **Uploads:**
  - Extension allow-list plus magic-byte check.
  - Streamed to disk with a size limit and a SHA-256 hash.
  - PDF page cap.
  - Files are stored under random keys outside any served directory.
- **Validation:** every field is checked by Pydantic schemas (lengths, enums, ranges).
- **PDF export:** all user and LLM text is HTML-escaped before rendering.

### LLM-specific risks

- **Untrusted text is fenced.** Web snippets and document chunks go into prompts inside
  delimited blocks, with the instruction to treat them as data. Web text is sanitized
  first: markup stripped, URLs normalized, `javascript:`/`data:` links dropped.
- **Structured outputs only.** Every agent response is validated against a schema.
  Citations are checked against the evidence actually supplied, and unsupported claims
  are removed.
- **Brand guardrails.** Restrictions such as banned phrases are enforced by a
  deterministic check after generation, not only by the prompt.
- **Workflow limits.** Revision loops are bounded (at most 2 automatic revisions), and a
  concept needs human approval before production.
- **Credit budget.** Each web-research run is capped at a fixed number of searches.

### HTTP hardening

- **API headers:** `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  `Cross-Origin-Opener-Policy`, CSP `default-src 'none'` (except `/docs`), and
  `Cache-Control: no-store` on all API data. Set `HSTS_ENABLED=true` once the API is
  served over HTTPS.
- **Web app headers:**
  - CSP: `connect-src` is limited to this app and the API, `frame-ancestors 'none'`, and
    `object-src`, `base-uri` and `form-action` are locked down.
  - Also `nosniff`, a `Permissions-Policy`, and no `X-Powered-By` header.
- **CORS:** an explicit origin allow-list. A wildcard is rejected at startup outside
  local and test.
- **Errors:** every error uses one envelope with a request ID. Stack traces are only
  logged, never returned.

### Configuration guards (staging and production)

Startup fails if:

- `JWT_SECRET_KEY` is the development default or shorter than 32 characters;
- `DEBUG` is on;
- `CORS_ORIGINS` contains `*`.

Secrets (`GOOGLE_API_KEY`, `TAVILY_API_KEY`, `LANGSMITH_API_KEY`, `QDRANT_API_KEY`) are
`SecretStr` values, so they are masked in logs and reprs. They are read only from the
environment or `.env`, which is git-ignored.

## Known gaps (accepted for now)

1. **No email flows.** There is no email verification, invitation emails or password
   reset (no email provider yet). Locked-out users must wait for the window to expire.
2. **Inline scripts in the web CSP.** Next.js hydration needs `'unsafe-inline'` scripts.
   Nonces would force fully dynamic rendering.
3. **Rate limits are per user, not per organization.** An organization with many users
   can spend more. Add organization-level spend quotas before a public launch.
4. **Rate limits fail open when Redis is down** (see above).
5. **Uploaded files are not virus-scanned.** They are only parsed (text extraction) and
   never served back raw. Add ClamAV or a cloud scanner if raw downloads are ever
   offered.
6. **No coverage report yet.** `pytest-cov` is not installed (see ROADMAP).

## Reporting

Report a vulnerability privately to the repository owner. Please don't open a public
issue.
