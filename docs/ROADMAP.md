# AdGenius AI — Build Roadmap

The project is built one phase at a time. Each phase ends with passing tests and a commit.

| Phase | Scope | Key tech | Status |
|------:|-------|----------|--------|
| 0 | Repo setup, backend foundation (config, logging, request IDs, error envelope, health check, tests) | FastAPI, Pydantic Settings, pytest | ✅ Done |
| 1 | Database layer: async SQLAlchemy, base models (UUID, timestamps), Alembic migrations | PostgreSQL, SQLAlchemy 2, Alembic | ⏳ Next |
| 2 | Auth & organizations: register/login, JWT + refresh-token rotation, memberships, RBAC (owner/admin/member) | passlib/argon2, PyJWT | |
| 3 | Brand management CRUD with org-level isolation | FastAPI, SQLAlchemy | |
| 4 | Document upload + async ingestion pipeline (validate → store → extract → chunk → embed → index) | Celery, Redis, PyMuPDF, python-docx, Qdrant | |
| 5 | Advanced RAG engine: query rewriting, hybrid search, fusion, reranking, citations, retrieval eval | LangChain, Qdrant | |
| 6 | Live web research tool with cached, cited results | Tavily | |
| 7 | Multi-agent workflow: 6 agents, parallel research, human approval interrupt, critic loop | LangGraph, Postgres checkpointer | |
| 8 | Campaigns, versioned runs, approvals, outputs APIs, SSE event stream | FastAPI, Celery, SSE | |
| 9 | Quality evaluation dashboard data, PDF export, LangSmith tracing | LangSmith, PDF renderer | |
| 10 | Frontend foundation: Next.js app shell, auth, dashboard, brands, documents | Next.js, TS, Tailwind, shadcn/ui, TanStack Query | |
| 11 | Frontend campaign flow: wizard, live execution view, concept selection, script/storyboard editors, critic view | Next.js | |
| 12 | Hardening: security review, rate limiting, test coverage, RAG/agent evaluation | | |
| 13 | Containerization & deployment (deferred) | Docker | |

## Local services needed (no Docker for now)

Phases 1+ need services running locally on Windows:

- **PostgreSQL 16+** — native Windows installer (phase 1).
- **Redis** — Memurai (Redis-compatible for Windows) or Redis inside WSL (phase 4).
- **Qdrant** — Windows binary from Qdrant's GitHub releases, or the free Qdrant Cloud tier (phase 4).
