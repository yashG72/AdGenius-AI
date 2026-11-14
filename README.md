# AdGenius AI

A multi-agent generative AI platform that works like a virtual creative advertising agency.
Specialized AI agents research a brand (RAG over uploaded documents) and its competitors
(live web search), develop creative concepts, write scripts, build storyboards with
image-generation prompts, and critique the result before a human approves it.

> **Status:** Phase 1 (database layer) complete. See [docs/ROADMAP.md](docs/ROADMAP.md) for the phase plan.

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
│   │   ├── api/             HTTP layer (deps + versioned routers)
│   │   └── schemas/         Pydantic request/response models
│   ├── alembic/             Database migrations
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

Health checks: `GET /api/v1/health` (liveness) and `GET /api/v1/health/ready` (database).

### Database migrations

```powershell
alembic revision --autogenerate -m "describe change"   # after editing a model - then REVIEW the file
alembic upgrade head                                   # apply
alembic downgrade -1                                   # undo the last migration
```

A test (`test_migrations_match_models`) fails if a model changes without a matching migration.

## API conventions

- All endpoints live under `/api/v1`.
- Every response carries an `X-Request-ID` header (used to correlate logs).
- Every error has the same shape:

```json
{ "error": { "code": "not_found", "message": "Resource not found.", "details": null, "request_id": "..." } }
```
