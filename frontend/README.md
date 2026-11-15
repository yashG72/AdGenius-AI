# AdGenius AI — frontend

Next.js 16 (App Router, Turbopack, `cacheComponents`) · React 19 · TypeScript · Tailwind CSS 4 ·
shadcn/ui (Radix) · TanStack Query · openapi-fetch.

## Run it

```powershell
npm install
copy .env.example .env.local      # only if the API is not on http://localhost:8000
npm run dev                        # http://localhost:3000  (backend must be running)
```

| Script | What it does |
|---|---|
| `npm run dev` / `build` / `start` | develop / production build / serve the build |
| `npm run typecheck` | regenerate Next route types, then `tsc --noEmit` |
| `npm run lint` | ESLint (incl. React Hooks + React Compiler rules) |
| `npm run gen:api` | regenerate `src/lib/api/schema.d.ts` from `openapi.json` |
| `npm run test:e2e` | Playwright smoke test against a running stack |

## How it fits together

- **Typed API client** — `backend: python -m scripts.export_openapi` writes
  `src/lib/api/openapi.json`; `npm run gen:api` turns it into TypeScript types. Every call
  through `api` (openapi-fetch) is checked against the real backend contract.
- **Auth** — the refresh token lives in an **httpOnly cookie** handled only by the route
  handlers in `src/app/api/auth/*` (login / refresh / logout). The browser keeps just the
  short-lived access token in memory. Refreshing is single-flight (the backend revokes a
  session when a refresh token is reused), and a 401 is retried once after refreshing.
- **Routing** — `/login`, `/register`, `/orgs` (workspace picker), and
  `/orgs/[orgId]/{dashboard,brands,brands/[brandId],settings}`. The workspace lives in the
  URL, so links are shareable.
- **Data** — TanStack Query hooks in `src/lib/queries/*`. Document lists poll only while
  something is still being indexed.
- **Theme** — dark charcoal + amber tokens in `src/app/globals.css` (`.dark`); the app is
  dark-only.

## End-to-end test

Start PostgreSQL, Redis, Qdrant, the API (`:8000`) and a Celery worker, then:

```powershell
npm run build; npm start            # in one terminal
npm run test:e2e                    # in another
```

The test registers a user, creates a workspace and brand, edits the profile, uploads a
document, waits for indexing, checks the dashboard and settings, and signs out.
