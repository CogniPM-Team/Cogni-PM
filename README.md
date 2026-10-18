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
    gateway/jira.py     Jira Cloud REST client          <- implemented and tested
    gateway/            MCP gateway: level-scoped tools, guardrails      (to build)
    orchestrator/       LangGraph agent runs, MCP client                 (to build)
    api/                FastAPI routes for the frontend                  (to build)
    db/                 PostgreSQL access and migrations                 (to build)
    rag/                embeddings + pgvector retrieval                  (to build)
  scripts/              check_connection.py: live Jira smoke test
  tests/                pytest
frontend/               React + TypeScript + Vite                        (to build)
  src/                  api/ assets/ components/ hooks/ lib/ pages/ styles/ - folders only
docs/architecture.md    the design decisions you need before writing code
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

pytest                                  # no network or credentials needed
python scripts/check_connection.py      # reads your real Jira site; changes nothing
```

`check_connection.py` also prints your site's story-points field id: copy it into `.env` as
`JIRA_STORY_POINTS_FIELD`. It differs per Jira site, so it must never be hardcoded.

## Where to start

Read [docs/architecture.md](docs/architecture.md) first. The pieces are fairly independent:

1. **MCP gateway** (`backend/cognipm/gateway/`): the heart of the project. Per-level tool registration plus guardrails.
2. **Database** (`backend/cognipm/db/`): decide the data model (runs, staged changes, approval tokens, audit log).
3. **API** (`backend/cognipm/api/`): the human's decisions: approve, reject, authorise.
4. **Orchestrator** (`backend/cognipm/orchestrator/`): LangGraph, calling the gateway as an MCP client.
5. **Frontend** (`frontend/`): see [frontend/README.md](frontend/README.md).
6. **RAG** (`backend/cognipm/rag/`): after the data model exists.

How we work (branches, PRs, checks): [CONTRIBUTING.md](CONTRIBUTING.md). Working agreements for
people and AI assistants: [CLAUDE.md](CLAUDE.md).
