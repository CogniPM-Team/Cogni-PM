# CogniPM

A control plane for agentic project management, built on top of Jira.

Jira owns the project data: issues, sprints, estimates. CogniPM owns the **oversight layer**: how a human
delegates work to an AI agent, at what level of autonomy, and how they review what comes back. It is a
final-year research project (Monash FIT4701); the contribution is the oversight architecture, not the feature
count.

**The core rule:** autonomy is enforced by which tools the agent is given, not by what a prompt asks it to do.
The Co-Pilot is only ever offered two read tools. The Super-Pilot can only stage drafts. Nothing reaches Jira
until a person approves it.

## What works today (the MVP)

| Screen | What you can do |
|---|---|
| **Agent console, Co-Pilot** | Ask questions about your Jira project in plain words (read only). Chats are saved, with folders, rename, delete and drag and drop. |
| **Agent console, Super-Pilot** | **Draft backlog:** paste requirements or meeting notes and the agent drafts stories. **Break down a story:** split an open story into sub-tasks. Both show their steps live. |
| **Approvals** | Review each draft beside the passage it quotes, edit it, tick the ones you want, confirm, and the issues are created in Jira. Reject, or regenerate with a note. |
| **Activity log** | Every step an agent took and every decision you made, with filters and a CSV export. It cannot be edited or deleted. |

How it fits together, with diagrams: [docs/architecture.md](docs/architecture.md). The build plan and what is
still to come (login, Auto-Pilot, RAG): [docs/phases.md](docs/phases.md).

## Stack

React + TypeScript + Vite (frontend) · Python + FastAPI (API) · LangGraph (agent runs) · an MCP gateway that
decides which tools each mode gets · PostgreSQL (oversight records) · Jira Cloud (project data) · Gemini (model).

## Before you start

You need:

| Thing | Notes |
|---|---|
| **Git** | |
| **Python 3.11 or newer** | |
| **Node 24.15 or newer** | Older Node fails the frontend tests (`jsdom` needs it). |
| **Docker Desktop** | Runs PostgreSQL. Without Docker see [No Docker?](#no-docker) |
| **A Jira Cloud site, a project, and an [API token](https://id.atlassian.com/manage-profile/security/api-tokens)** | **Use a sandbox project.** Approving a draft creates a real issue there. |
| **A [Gemini API key](https://aistudio.google.com/apikey) with credit** | Drafting and the Co-Pilot call the model. A key with no credit fails with HTTP 402. |

## Get it running

Three things run side by side: Postgres, the API and the website. Use a separate terminal for each.

### 1. Clone and configure

```bash
git clone https://github.com/CogniPM-Team/Cogni-PM.git
cd Cogni-PM
cp .env.example .env        # Windows PowerShell: Copy-Item .env.example .env
```

Open `.env` and fill in `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` and `GEMINI_API_KEY`.
`.env` is git-ignored: never commit it or paste its values anywhere. You fill in `JIRA_STORY_POINTS_FIELD` in
step 3.

### 2. Start PostgreSQL

```bash
docker run -d --name cognipm-db -p 5432:5432 \
  -e POSTGRES_USER=cognipm -e POSTGRES_PASSWORD=cognipm -e POSTGRES_DB=cognipm \
  -v cognipm-db-data:/var/lib/postgresql/data pgvector/pgvector:pg16
```

(On Windows PowerShell write it on one line, without the `\` line breaks.) The `-v` keeps your data when the
container restarts. Later: `docker start cognipm-db` / `docker stop cognipm-db`.

**Port 5432 already in use?** You may already run PostgreSQL. Use `-p 5433:5432` instead and add this line to
`.env`: `DATABASE_URL=postgresql://cognipm:cognipm@localhost:5433/cognipm`

### 3. Start the API

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python scripts/check_connection.py # reads your Jira site; changes nothing
```

`check_connection.py` prints your site's story-points field id. Copy it into `.env` as `JIRA_STORY_POINTS_FIELD`
(it differs per Jira site, so it is never hardcoded). Then:

```bash
uvicorn cognipm.api.main:app --reload
```

The API is at <http://localhost:8000> and its interactive docs are at <http://localhost:8000/docs>. It creates
the database tables itself on first start.

### 4. Start the website

```bash
cd frontend
npm install
npm run dev
```

Open **<http://localhost:5173>**. The dev server forwards `/api` to the API on port 8000.

> **There is no login yet.** Anyone who can reach the API can approve a write to Jira. Run it on your own machine
> only; do not expose it to a network.

## Try it

1. **Co-Pilot:** type "Which stories are still open?". It reads your Jira project and answers. Your chat appears in
   the list on the left.
2. **Super-Pilot, Draft backlog:** switch to Super-Pilot, paste the text from
   [docs/sample-notes.md](docs/sample-notes.md), and start the task. Watch the steps, then open **Review and
   approve**.
3. **Approvals:** every draft shows its reasoning, assumptions and the highlighted quote. Tick one, press
   **Approve and create**, confirm, and the issue appears in your Jira project with the label `cognipm-drafted`.
   Nothing is ticked by default, on purpose.
4. **Activity log:** see every step you just triggered.

## Run the tests

**Backend** (from `backend/`):

```bash
docker exec cognipm-db createdb -U cognipm cognipm_test      # once: a separate database for the tests
DATABASE_URL=postgresql://cognipm:cognipm@localhost:5432/cognipm_test pytest -q
ruff check . && ruff format --check .
```

(PowerShell: `$env:DATABASE_URL="postgresql://cognipm:cognipm@localhost:5432/cognipm_test"; pytest -q`. If you
used port 5433, change it in the URL.)

> **The tests wipe their database** (every test rebuilds the schema), so they must never point at the database the
> app uses. They refuse any database whose name does not contain `test`, and say so. No Jira site or Gemini key is
> needed: the tests use fakes.

**Frontend** (from `frontend/`):

```bash
npm test                     # unit and component tests
npm run lint && npx tsc --noEmit
npm run build
```

These are the same checks CI runs on every pull request.

### Live checks against your real Jira (optional)

Scripts in `backend/scripts/` talk to your real project, so read what each does first. Run them from `backend/`:

| Script | Effect |
|---|---|
| `check_connection.py` | Reads the site and prints issue types and the story-points field. Changes nothing. |
| `demo_stage.py` | Runs the gateway at each mode and stages a draft. Reads Jira, writes nothing. |
| `demo_guardrails.py` | Tries bad drafts and shows each refused and logged. Reads Jira, creates nothing. |
| `demo_run.py` | A real Gemini run (sends synthetic text; uses credit). Reads Jira, creates nothing. |
| `verify_write.py --confirm` | **Creates two issues**, then deletes or closes them. |
| `demo_flow.py --confirm` | **The whole flow through the API: creates one issue**, then closes it. Uses Gemini. |

Each prints before and after state so you can see nothing is left behind.

## Troubleshooting

| You see | Do this |
|---|---|
| `password authentication failed for user "cognipm"` | Something else is using port 5432. Use `-p 5433:5432` and set `DATABASE_URL` as in step 2. |
| `Refusing to run the tests against database 'cognipm'` | Working as intended. Use the `cognipm_test` database (see Run the tests). |
| The website loads but shows "Could not load" | The API is not running, or cannot reach Postgres. Check the API terminal. |
| Drafting fails with `402` / "credits depleted" | The Gemini key has no credit. Top it up or use another key. |
| `Jira returned 401` | Wrong `JIRA_EMAIL` or `JIRA_API_TOKEN`. The token belongs to the email's Atlassian account. |
| Creating a draft fails naming a required field | Your Jira project requires a field a draft cannot fill. Add a default for it in Jira. |
| `npm test` fails with an engine or `jsdom` error | Upgrade Node to 24.15 or newer. |
| `uvicorn: command not found` | Activate the backend virtualenv, then `pip install -e ".[dev]"` again. |

### No Docker?

Install the embedded database instead: `pip install -e ".[embedded-db]"`. The tests then start a throwaway
Postgres by themselves. To run the app itself you still need a Postgres you can point `DATABASE_URL` at.

## Repository layout

```
backend/
  cognipm/
    gateway/       jira.py (Jira client), server.py (mode-scoped MCP tools), apply.py (the one write path),
                   guardrails.py (the nine rules)
    orchestrator/  LangGraph runs: P1 draft backlog, P2 break down a story, the Co-Pilot chat
    api/           FastAPI control plane: runs, review, chat, audit
    db/            PostgreSQL schema, migrations, append-only audit log
    rag/           embeddings and retrieval (not built yet)
  scripts/         live checks (above) and the OpenAPI export
  tests/           pytest
frontend/src/      api/ components/ hooks/ lib/ pages/ styles/ test/
docs/              architecture.md, phases.md, sample-notes.md
.mcp.json          lets Claude Code drive the gateway at M1, M2 or M3 by hand
.github/           CI, PR template, Dependabot
```

## Working on it

Read [docs/architecture.md](docs/architecture.md) first: its decisions are settled, and if you think one is
wrong, say so in a PR rather than building around it. How we work (branches, PRs, checks):
[CONTRIBUTING.md](CONTRIBUTING.md). Working agreements for people and AI assistants: [CLAUDE.md](CLAUDE.md).
Frontend details: [frontend/README.md](frontend/README.md).
