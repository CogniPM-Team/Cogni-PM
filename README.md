# CogniPM

A control plane for agentic project management, built on top of Jira.

Jira owns the project data: issues, sprints, estimates. CogniPM owns the **oversight layer**: how a
human delegates work to an AI agent, at what level of autonomy, and how they review what comes back.
It is a final-year research project (Monash FIT4701); the contribution is the oversight architecture,
not the feature count.

> **Status: project skeleton.** Only the Jira connection is implemented. The database, orchestrator,
> API and frontend are empty folders waiting to be built. See [Where to start](#where-to-start).

## Intended stack

| Area | Technology |
|---|---|
| Frontend | React, TypeScript, Vite |
| Backend | Python, FastAPI |
| Agent orchestration | LangGraph, with controlled tool access through an MCP gateway |
| Data | Jira Cloud (project data), PostgreSQL + pgvector (oversight records, RAG retrieval) |
| Model | Gemini |
| Testing | pytest, Jira and manual testing |

## Repository layout

```
backend/
  cognipm/
    gateway/jira.py     Jira Cloud REST client                           <- implemented and tested
    gateway/server.py   MCP gateway: mode-scoped tools (M1/M2/M3)       <- implemented and tested
    gateway/apply.py    the one place a draft becomes a Jira issue       <- implemented and tested
    gateway/guardrails.py  validator chain (empty; Phase 4 fills it)
    orchestrator/       LangGraph runs (P1, P2, M1 chat), MCP client     <- implemented and tested
    api/                FastAPI routes for the frontend                  (to build)
    db/                 PostgreSQL schema, migrations, audit log         <- implemented and tested
    rag/                embeddings + pgvector retrieval                  (to build)
  scripts/              check_connection.py, verify_write.py, demo_stage.py: live smoke tests
  tests/                pytest
frontend/               React + TypeScript + Vite                        (to build)
  src/                  api/ assets/ components/ hooks/ lib/ pages/ styles/ - folders only
docs/architecture.md    the design decisions you need before writing code
docs/phases.md          the build plan, phase by phase
.mcp.json               lets Claude Code drive the gateway at M1, M2 or M3 by hand
.github/                CI, PR template, Dependabot
```

## Getting started

You need Python 3.11+ and a Jira Cloud site with an
[API token](https://id.atlassian.com/manage-profile/security/api-tokens).

```bash
cp .env.example .env          # then fill in the JIRA_* values
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

pytest                                  # no network or credentials needed (see the database note below)
python scripts/check_connection.py      # reads your real Jira site; changes nothing
python scripts/demo_stage.py            # runs the gateway at M1, M2, M3 over stdio; reads Jira, writes nothing
python scripts/demo_run.py              # a real Gemini P1 + P2 run (needs GEMINI_API_KEY; sends synthetic text)
```

**Database.** The tests and the gateway need PostgreSQL. Either start one and point `DATABASE_URL` at it
(`docker run -d -p 5432:5432 -e POSTGRES_USER=cognipm -e POSTGRES_PASSWORD=cognipm -e POSTGRES_DB=cognipm pgvector/pgvector:pg16`,
the same image CI uses), or run `pip install -e ".[embedded-db]"` and the tests start a throwaway server by
themselves. With neither, the database tests are skipped locally and fail in CI.

`check_connection.py` also prints your site's story-points field id: copy it into `.env` as
`JIRA_STORY_POINTS_FIELD`. It differs per Jira site, so it must never be hardcoded.

## Where to start

Read [docs/architecture.md](docs/architecture.md) first. The pieces are fairly independent:

1. **MCP gateway** (`backend/cognipm/gateway/`): the heart of the project. Built: per-mode tool registration.
   Next: the guardrail chain (Phase 4).
2. **Database** (`backend/cognipm/db/`): built (runs, staged drafts, approval tokens, audit log).
3. **API** (`backend/cognipm/api/`): the human's decisions: approve, reject, authorise.
4. **Orchestrator** (`backend/cognipm/orchestrator/`): LangGraph, calling the gateway as an MCP client.
5. **Frontend** (`frontend/`): see [frontend/README.md](frontend/README.md).
6. **RAG** (`backend/cognipm/rag/`): after the data model exists.

How we work (branches, PRs, checks): [CONTRIBUTING.md](CONTRIBUTING.md). Working agreements for
people and AI assistants: [CLAUDE.md](CLAUDE.md).
