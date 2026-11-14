# AdGenius AI

A multi-agent generative AI platform that works like a virtual creative advertising agency.
Specialized AI agents research a brand (RAG over uploaded documents) and its competitors
(live web search), develop creative concepts, write scripts, build storyboards with
image-generation prompts, and critique the result before a human approves it.

> **Status:** Phase 0 (foundation). See [docs/ROADMAP.md](docs/ROADMAP.md) for the phase plan.

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
│   │   ├── api/             HTTP layer (deps + versioned routers)
│   │   └── schemas/         Pydantic request/response models
│   └── tests/               pytest suite
├── frontend/                Next.js app (added in phase 10)
└── docs/                    Roadmap and design notes
```

## Backend: local setup (Windows / PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env

uvicorn app.main:app --reload       # http://localhost:8000/docs
pytest                              # run tests
ruff check .                        # lint
```

Health check: `GET http://localhost:8000/api/v1/health`

## API conventions

- All endpoints live under `/api/v1`.
- Every response carries an `X-Request-ID` header (used to correlate logs).
- Every error has the same shape:

```json
{ "error": { "code": "not_found", "message": "Resource not found.", "details": null, "request_id": "..." } }
```
