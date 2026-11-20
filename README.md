# AdGenius AI

**Live demo:** https://adgenius-ai-peach.vercel.app (free hosting: the first visit after a quiet spell can take up to a minute)

A multi-agent generative AI platform that works like a virtual creative advertising agency.
Specialized AI agents research a brand (RAG over uploaded documents) and its competitors
(live web search), develop creative concepts, write scripts, build storyboards with
image-generation prompts, and critique the result before a human approves it.

> **Status:** Phase 11 complete — the full product works end to end in the browser: brief →
> live multi-agent run → concept approval → evaluation → script/storyboard editing → PDF.
> Frontend docs: [frontend/README.md](frontend/README.md). See [docs/RAG_EVALUATION.md](docs/RAG_EVALUATION.md)
> for how retrieval settings were chosen. See [docs/ROADMAP.md](docs/ROADMAP.md) for the phase plan.
> **New to the code?** Start with [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): every file and
> how they work together, flow by flow. **Deploying?** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
> puts the whole stack on free plans (Render, Vercel, Neon, Qdrant Cloud) - no Docker needed.

## Tech stack

| Layer | Technology |
|-------|-----------|
| API | Python 3.11+, FastAPI, Pydantic |
| Data | PostgreSQL (SQLAlchemy async + Alembic), Qdrant (vectors), Redis |
| Async work | Celery |
| AI | LangChain, LangGraph, LangSmith, Tavily |
| Frontend | Next.js, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query |

## Repository layout

```
AdGenius-AI/
├── backend/                 FastAPI service
│   ├── app/
│   │   ├── main.py          App factory + entry point
│   │   ├── core/            Config, logging, middleware, errors
│   │   ├── db/              SQLAlchemy base, mixins, engine/session
│   │   ├── models/          ORM models (one file per table)
│   │   ├── services/        Business logic (auth, organizations, ...)
│   │   ├── ingestion/       Document pipeline: validate, extract, chunk, embed, index
│   │   ├── worker/          Celery app, background tasks, dispatch helpers
│   │   ├── rag/             Retrieval, rewriting, reranking, grounded answers, metrics
│   │   ├── llm/             Structured LLM client (Gemini via LangChain)
│   │   ├── research/        Live web research (Tavily), caching, competitor reports
│   │   ├── agents/          LangGraph multi-agent workflow (6 agents, checkpoints)
│   │   ├── campaigns/       Worker-side run execution + live progress recording
│   │   ├── api/             HTTP layer (deps + versioned routers)
│   │   └── schemas/         Pydantic request/response models
│   ├── alembic/             Database migrations
│   ├── evals/               Labelled datasets for evaluation
│   ├── scripts/             CLI tools (e.g. scripts/eval_retrieval.py)
│   └── tests/               pytest suite (runs against a real test database)
├── frontend/                Next.js 16 app (TypeScript, Tailwind, shadcn/ui, TanStack Query)
│   ├── src/app/             Routes: (auth), orgs/[orgId]/…, api/auth/* (cookie handlers)
│   ├── src/lib/             Typed API client, auth, query hooks
│   └── e2e/                 Playwright smoke test
└── docs/                    Roadmap and design notes
```

## Backend: local setup (Windows / PowerShell)

Prerequisite: PostgreSQL 17 running locally with a role and two databases:

```sql
CREATE ROLE adgenius LOGIN PASSWORD '<choose-one>';
CREATE DATABASE adgenius OWNER adgenius;
CREATE DATABASE adgenius_test OWNER adgenius;
```

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env              # then put your password into the two DB URLs

alembic upgrade head                # create/upgrade tables in the dev database
uvicorn app.main:app --reload       # http://localhost:8000/docs
pytest                              # run tests (resets adgenius_test)
ruff check .                        # lint
```

Health checks: `GET /api/v1/health` (liveness) and `GET /api/v1/health/ready`
(database, Redis, Qdrant).

### Background services

```powershell
powershell -File $env:USERPROFILE\redis8\start-redis.ps1    # 1. Redis (job queue, cache, rate limits)
powershell -File $env:USERPROFILE\qdrant\start-qdrant.ps1   # 2. vector DB
uvicorn app.main:app --reload                               # 3. API
# 4. workers - one per queue, so a long campaign never delays document indexing
celery -A app.worker.celery_app worker --pool=solo -Q default -n default@%h --loglevel=info
celery -A app.worker.celery_app worker --pool=solo -Q campaigns -n campaigns@%h --loglevel=info
celery -A app.worker.celery_app beat --loglevel=info        # 5. optional: daily housekeeping
```

A single worker can serve both queues with `-Q default,campaigns`, but a worker started
**without** `-Q` only listens to `default` - campaign runs would then wait in `queued`.

PostgreSQL runs as a Windows service. On Windows, Celery needs `--pool=solo`. Uploaded
documents stay `pending` until a worker picks them up.

### Database migrations

```powershell
alembic revision --autogenerate -m "describe change"   # after editing a model - then REVIEW the file
alembic upgrade head                                   # apply
alembic downgrade -1                                   # undo the last migration
```

A test (`test_migrations_match_models`) fails if a model changes without a matching migration.

## API conventions

- All endpoints live under `/api/v1`. Interactive docs at `/docs`.
- Auth: `POST /auth/login` returns an access token (15 min) and a refresh token (30 days).
  Send `Authorization: Bearer <access_token>`; call `POST /auth/refresh` for a new pair
  (each refresh token works once).
- Collections are returned as `{"items": [...]}`; paginated ones add `total`, `limit`, `offset`.
- Users only see organizations (and their brands) they belong to; everything else is `404`.
- Organization-scoped collections take `?organization_id=...` (e.g. `GET /brands`).
- Too many requests return `429` with a `Retry-After` header (see [docs/SECURITY.md](docs/SECURITY.md)).
- Request bodies over 1 MB (uploads: 26 MB) return `413`.
- Deleting a brand is a soft delete (history is kept; it disappears from the API).

### Campaign flow

```
POST /campaigns                         create (brief stored on the campaign)
POST /campaigns/{id}/generate           -> run v1 (queued; the worker runs the agents)
GET  /campaign-runs/{run_id}/events     live SSE: agent steps, status changes, end
GET  /campaign-runs/{run_id}            status, trace, pending approval, output versions
POST /approvals/{id}/approve            {"concept_id": "C2"}   (or /reject {"feedback": ...})
GET  /campaign-runs/{run_id}/script     also /concepts /storyboard /evaluation (?version=n)
POST /campaign-runs/{run_id}/regenerate new version from the current brief (old kept)
POST /campaign-runs/{run_id}/retry      continue a failed run from its last checkpoint
GET  /campaign-runs/{run_id}/evaluation-summary   score trend, issues, revisions, timings
GET  /campaign-runs/{run_id}/export.pdf           finished campaign as a PDF (latest edits)
PUT  /campaign-runs/{run_id}/script               save an edited script as a new version
PUT  /campaign-runs/{run_id}/storyboard           save an edited storyboard as a new version
GET  /organizations/{id}/dashboard                totals, quality rates, recent activity
```

### Agent tracing (optional)

Set `LANGSMITH_API_KEY` (free at https://smith.langchain.com) in `backend/.env`. Every agent
step and LLM call is then traced in LangSmith, tagged with `organization_id`, `campaign_id`,
`run_id`, `run_version` and `attempt` for filtering.

The CLI (`python -m scripts.run_campaign`) drives the same workflow without the API.
- Every response carries an `X-Request-ID` header (used to correlate logs).
- Every error has the same shape:

```json
{ "error": { "code": "not_found", "message": "Resource not found.", "details": null, "request_id": "..." } }
```
