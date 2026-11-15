# AdGenius AI — Build Roadmap

The project is built one phase at a time. Each phase ends with passing tests and a commit.

| Phase | Scope | Key tech | Status |
|------:|-------|----------|--------|
| 0 | Repo setup, backend foundation (config, logging, request IDs, error envelope, health check, tests) | FastAPI, Pydantic Settings, pytest | ✅ Done |
| 1 | Database layer: async SQLAlchemy, base models (UUID, timestamps), Alembic migrations, organizations/users/memberships tables, readiness check | PostgreSQL 17, SQLAlchemy 2, Alembic | ✅ Done |
| 2 | Auth & organizations: register/login/logout, JWT access tokens, refresh-token rotation with reuse detection, profile & password change, organization + member APIs, RBAC (owner/admin/member) | argon2, PyJWT | ✅ Done |
| 3 | Brand management: full profile (JSONB for structured fields), validation, pagination/search, soft delete, org-level isolation | FastAPI, SQLAlchemy, JSONB | ✅ Done |
| 4 | Document upload + async ingestion pipeline (validate → store → extract → clean → chunk → embed dense+sparse → index), lifecycle statuses, delete & reindex | Celery, Memurai, PyMuPDF, python-docx, LangChain splitters, FastEmbed, Qdrant | ✅ Done |
| 5 | RAG engine: LLM query rewriting, hybrid dense+BM25 search with server-side RRF fusion, live-document check, optional cross-encoder reranking, context assembly, grounded answers with validated citations, retrieval evaluation harness | LangChain, Qdrant, FastEmbed, Gemini | ✅ Done |
| 6 | Live web research: sanitized Tavily search, Redis cache (results + query plans), credit budget, evidence-grounded competitor report with validated citations and timestamps | Tavily, Redis, Gemini | ✅ Done |
| 7 | Multi-agent workflow: 6 agents with structured outputs, parallel research branches, human concept-approval interrupt, critic revision loop (threshold 80, max 2 revisions, then human review), deterministic routing, retry policies, durable PostgreSQL checkpoints, execution trace, optional LangSmith, CLI runner | LangGraph, Postgres checkpointer, Gemini | ✅ Done |
| 8 | Campaigns API: versioned runs with brief/brand snapshots, idempotent worker execution (start / resume / continue), live progress persistence, approvals API, versioned outputs, retry & regenerate, SSE event stream with Last-Event-ID resume | FastAPI, Celery, SSE | ✅ Done |
| 9 | Campaign PDF export (PyMuPDF HTML renderer, escaped untrusted text), per-run evaluation summary (score trend, issues, revisions, agent timings), organization dashboard (totals, quality rates, activity, recent items), LangSmith trace metadata | PyMuPDF, LangSmith | ✅ Done |
| 10 | Frontend foundation: typed API client from OpenAPI, httpOnly-cookie auth (BFF route handlers, single-flight refresh), login/register, workspace picker & switcher, dashboard, brands + full profile editor, knowledge base (upload, live status, reindex, delete), settings (account, workspace, members/roles), Playwright E2E | Next.js 16, TS, Tailwind 4, shadcn/ui, TanStack Query, Playwright | ✅ Done |
| 11 | Campaign UI: list, 4-step brief wizard (create/edit), campaign history, run workspace with live agent pipeline (fetch-based SSE + Last-Event-ID), concept approval/rejection, research/concepts views, versioned script & storyboard editors (backend: human edits saved as new versions), Critic evaluation dashboard (validated chart palette), PDF download, regenerate/retry; full-product Playwright test with real agents | Next.js, SSE, Playwright | ✅ Done |
| 12 | Hardening: security review, rate limiting, test coverage, RAG/agent evaluation | | ⏳ Next |
| 13 | Containerization & deployment (deferred) | Docker | |

## Deferred items (tracked so they aren't forgotten)

- Login rate limiting / brute-force protection (phase 12, needs Redis).
- Periodic cleanup of expired/revoked refresh tokens (Celery beat, phase 4+).
- Email invitations and email verification (needs an email provider).
- Web clients: consider keeping the refresh token in an httpOnly cookie (phase 10).
- Web research: prefer recent sources for trend queries (Tavily `time_range`) — live runs
  occasionally cite years-old articles; competitor research takes ~35–50 s, so phase 7 runs
  it inside the worker.
- Agent workflow: the competitor-research plan cache misses between campaign runs because
  the Campaign Manager's LLM-written research focus is part of the cache key (~6 Tavily
  credits per run). Key the plan on brand + brief fields instead.
- Worker: one `--pool=solo` worker processes ingestion and campaign tasks in sequence, so a
  long campaign delays document indexing. In deployment, route `campaigns.*` to its own queue
  and worker.
- SSE: browsers' native `EventSource` cannot send an Authorization header; the frontend
  (phase 10) should use a fetch-based SSE client.

## Local services needed (no Docker for now)

Phases 1+ need services running locally on Windows:

- **PostgreSQL 17** — installed via `winget install PostgreSQL.PostgreSQL.17`, runs as the
  `postgresql-17` Windows service. App role `adgenius` owns databases `adgenius` (dev) and
  `adgenius_test` (wiped by every test run).
- **Redis 8.10.3** — portable community Windows build ([redis-windows](https://github.com/redis-windows/redis-windows))
  in `%USERPROFILE%\redis8`; start with `powershell -File $env:USERPROFILE\redis8\start-redis.ps1`
  (localhost only, `noeviction` so queued jobs are never dropped). Memurai's MSI fails on this
  machine (error 1603), and Redis 5.x is too old for current Celery (needs ≥ 6.2).
- **Qdrant 1.20** — Windows binary in `%USERPROFILE%\qdrant`; start it with
  `powershell -File $env:USERPROFILE\qdrant\start-qdrant.ps1` (localhost only, dashboard at
  http://127.0.0.1:6333/dashboard).

## AI model choices (free)

- **Embeddings:** local FastEmbed models, no API key. Dense `jinaai/jina-embeddings-v2-small-en`
  (512-dim, 8192-token input, so ~800-token chunks are never truncated) + sparse `Qdrant/bm25`
  for keyword matching. Downloaded once to `~/.cache/adgenius/fastembed`.
- **LLM (phase 5+):** Google Gemini via the free AI Studio API tier.
