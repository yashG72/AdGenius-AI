# AdGenius AI — Build Roadmap

The project is built one phase at a time. Each phase ends with passing tests and a commit.

| Phase | Scope | Key tech | Status |
|------:|-------|----------|--------|
| 0 | Repo setup, backend foundation (config, logging, request IDs, error envelope, health check, tests) | FastAPI, Pydantic Settings, pytest | ✅ Done |
| 1 | Database layer: async SQLAlchemy, base models (UUID, timestamps), Alembic migrations, organizations/users/memberships tables, readiness check | PostgreSQL 17, SQLAlchemy 2, Alembic | ✅ Done |
| 2 | Auth & organizations: register/login/logout, JWT access tokens, refresh-token rotation with reuse detection, profile & password change, organization + member APIs, RBAC (owner/admin/member) | argon2, PyJWT | ✅ Done |
| 3 | Brand management: full profile (JSONB for structured fields), validation, pagination/search, soft delete, org-level isolation | FastAPI, SQLAlchemy, JSONB | ✅ Done |
| 4 | Document upload + async ingestion pipeline (validate → store → extract → clean → chunk → embed dense+sparse → index), lifecycle statuses, delete & reindex | Celery, Memurai, PyMuPDF, python-docx, LangChain splitters, FastEmbed, Qdrant | ✅ Done |
| 5 | RAG engine: LLM query rewriting, hybrid dense+BM25 search with server-side RRF fusion, live-document check, optional cross-encoder reranking, context assembly, grounded answers with validated citations, retrieval evaluation harness | LangChain, Qdrant, FastEmbed, Gemini | ✅ Done (live LLM test pending API key) |
| 6 | Live web research tool with cached, cited results | Tavily | ⏳ Next |
| 7 | Multi-agent workflow: 6 agents, parallel research, human approval interrupt, critic loop | LangGraph, Postgres checkpointer | |
| 8 | Campaigns, versioned runs, approvals, outputs APIs, SSE event stream | FastAPI, Celery, SSE | |
| 9 | Quality evaluation dashboard data, PDF export, LangSmith tracing | LangSmith, PDF renderer | |
| 10 | Frontend foundation: Next.js app shell, auth, dashboard, brands, documents | Next.js, TS, Tailwind, shadcn/ui, TanStack Query | |
| 11 | Frontend campaign flow: wizard, live execution view, concept selection, script/storyboard editors, critic view | Next.js | |
| 12 | Hardening: security review, rate limiting, test coverage, RAG/agent evaluation | | |
| 13 | Containerization & deployment (deferred) | Docker | |

## Deferred items (tracked so they aren't forgotten)

- Login rate limiting / brute-force protection (phase 12, needs Redis).
- Periodic cleanup of expired/revoked refresh tokens (Celery beat, phase 4+).
- Email invitations and email verification (needs an email provider).
- Web clients: consider keeping the refresh token in an httpOnly cookie (phase 10).

## Local services needed (no Docker for now)

Phases 1+ need services running locally on Windows:

- **PostgreSQL 17** — installed via `winget install PostgreSQL.PostgreSQL.17`, runs as the
  `postgresql-17` Windows service. App role `adgenius` owns databases `adgenius` (dev) and
  `adgenius_test` (wiped by every test run).
- **Redis** — Memurai's MSI fails on this machine (error 1603). Portable Redis 5.0.14
  (tporadowski build) runs from `%USERPROFILE%\redis` via `start-redis.ps1` (localhost only,
  `noeviction`). It serves the API and readiness checks, but **current Celery/kombu needs
  Redis ≥ 6.2** (its Lua scripts fail on 5.x), so the worker needs a newer Redis build —
  pending a decision. redis-py is pinned `<8` because v8 requires RESP3 (Redis ≥ 6).
- **Qdrant 1.20** — Windows binary in `%USERPROFILE%\qdrant`; start it with
  `powershell -File $env:USERPROFILE\qdrant\start-qdrant.ps1` (localhost only, dashboard at
  http://127.0.0.1:6333/dashboard).

## AI model choices (free)

- **Embeddings:** local FastEmbed models, no API key. Dense `jinaai/jina-embeddings-v2-small-en`
  (512-dim, 8192-token input, so ~800-token chunks are never truncated) + sparse `Qdrant/bm25`
  for keyword matching. Downloaded once to `~/.cache/adgenius/fastembed`.
- **LLM (phase 5+):** Google Gemini via the free AI Studio API tier.
