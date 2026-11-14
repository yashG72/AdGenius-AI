# AdGenius AI

A multi-agent generative AI platform that works like a virtual creative advertising agency.
Specialized AI agents research a brand (RAG over uploaded documents) and its competitors
(live web search), develop creative concepts, write scripts, build storyboards with
image-generation prompts, and critique the result before a human approves it.

> **Status:** Phase 5 (RAG engine) complete. See [docs/RAG_EVALUATION.md](docs/RAG_EVALUATION.md)
> for how retrieval settings were chosen. See [docs/ROADMAP.md](docs/ROADMAP.md) for the phase plan.

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
│   │   ├── api/             HTTP layer (deps + versioned routers)
│   │   └── schemas/         Pydantic request/response models
│   ├── alembic/             Database migrations
│   ├── evals/               Labelled datasets for evaluation
│   ├── scripts/             CLI tools (e.g. scripts/eval_retrieval.py)
│   └── tests/               pytest suite (runs against a real test database)
├── frontend/                Next.js app (added in phase 10)
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

### Background services (three terminals)

```powershell
powershell -File $env:USERPROFILE\redis8\start-redis.ps1                 # 1. Redis (job queue)
powershell -File $env:USERPROFILE\qdrant\start-qdrant.ps1                # 2. vector DB
uvicorn app.main:app --reload                                            # 3. API
celery -A app.worker.celery_app worker --pool=solo --loglevel=info       # 4. worker
```

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
- Deleting a brand is a soft delete (history is kept; it disappears from the API).
- Every response carries an `X-Request-ID` header (used to correlate logs).
- Every error has the same shape:

```json
{ "error": { "code": "not_found", "message": "Resource not found.", "details": null, "request_id": "..." } }
```
