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

To **run** it you need:

| Thing | Notes |
|---|---|
| **Git** | |
| **Docker Desktop** | Runs everything: the app and its PostgreSQL database. |
| **A Jira Cloud site, a project, and an [API token](https://id.atlassian.com/manage-profile/security/api-tokens)** | **Use a sandbox project.** Approving a draft creates a real issue there. |
| **A [Gemini API key](https://aistudio.google.com/apikey) with credit** | Drafting and the Co-Pilot call the model. A key with no credit fails with HTTP 402. |

To **change the code and run the tests** you also need Python 3.11 or newer and Node 24.15 or newer (older Node fails
the frontend tests, because `jsdom` needs it).

## Get it running

### The easy way: one command (Docker)

```bash
git clone https://github.com/CogniPM-Team/Cogni-PM.git
cd Cogni-PM
cp .env.example .env        # Windows PowerShell: Copy-Item .env.example .env
```

Open `.env` and fill in `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` and `GEMINI_API_KEY`.
(If a teammate sent you a ready-made `.env`, just put it in the repo root.) `.env` is git-ignored: never commit it or
paste its values anywhere. Then:

```bash
docker compose up --build
```

The first run builds the image and takes a few minutes. When it settles, open **<http://localhost:8000>**: the
website and the API are the same address. The API docs are at <http://localhost:8000/docs>.

| Command | What it does |
|---|---|
| `docker compose up --build` | Build and start (add `-d` to run in the background) |
| `docker compose down` | Stop it. Your data is kept. |
| `docker compose down -v` | Stop it **and delete the database** |
| `docker compose logs -f app` | Watch the app's log |

It starts two containers: the app (the API with the built website, one image) and PostgreSQL. The app creates the
database tables itself on first start. Both ports are bound to your own machine only.

**A port is already in use?** Set another one for that run, for example
`COGNIPM_PORT=8010 COGNIPM_DB_PORT=5440 docker compose up` (PowerShell: `$env:COGNIPM_PORT=8010; docker compose up`).

**Updating.** After you pull new code, run `docker compose up --build` again. Your data is kept.

**Optional setting:** `JIRA_STORY_POINTS_FIELD` is the id of your site's story-points field (it differs per Jira
site). Drafting does not use it, so you can leave it empty. Only the Co-Pilot's answers about estimates need it.
`check_connection.py` prints the id (see the live checks below).

> **There is no login yet.** Anyone who can reach the app can approve a write to Jira. Run it on your own machine
> only; do not expose it to a network.

### For developers: run the pieces yourself

Use this when you are changing code and want hot reload. Run the database from Docker, and the API and the website
as normal processes, each in its own terminal.

```bash
docker compose up -d db                # PostgreSQL only, on localhost:5433
```

Add `DATABASE_URL=postgresql://cognipm:cognipm@localhost:5433/cognipm` to `.env`. Then the API:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn cognipm.api.main:app --reload
```

And the website, in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **<http://localhost:5173>**. The dev server forwards `/api` to the API on port 8000, so you see your changes
immediately.

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
docker compose up -d db                                        # the database, if it is not already running
docker compose exec db createdb -U cognipm cognipm_test        # once: a separate database for the tests
DATABASE_URL=postgresql://cognipm:cognipm@localhost:5433/cognipm_test pytest -q
ruff check . && ruff format --check .
```

(PowerShell: `$env:DATABASE_URL="postgresql://cognipm:cognipm@localhost:5433/cognipm_test"; pytest -q`. If you set
`COGNIPM_DB_PORT`, use that port in the URL.)

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

Scripts in `backend/scripts/` talk to your real project, so read what each does first. Run them from `backend/`
(developer setup), or inside the running app container with
`docker compose exec app sh -c "cd /app/backend && python scripts/check_connection.py"`:

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
| `password authentication failed for user "cognipm"` or `port is already allocated` | Another PostgreSQL or container is using the port. Set a free one: `COGNIPM_DB_PORT=5440` (and use it in `DATABASE_URL`). |
| `port is already allocated` on 5433, and you started a Postgres container by hand earlier (`docker run ... --name cognipm-db`) | The old manual container holds the port. Stop it with `docker stop cognipm-db` (it keeps its data; `docker rm cognipm-db` removes it), then run `docker compose up --build` again. The new setup starts with an empty database. |
| `docker compose up` says `.env` is missing | Copy `.env.example` to `.env` and fill it in (see "The easy way"). |
| The page at `localhost:8000` is blank or shows "Cannot GET" | The image has not finished building, or the build failed. Run `docker compose logs app`. |
| `Refusing to run the tests against database 'cognipm'` | Working as intended. Use the `cognipm_test` database (see Run the tests). |
| The website loads but shows "Could not load" | The app cannot reach Postgres or Jira. Run `docker compose logs app`. |
| Drafting fails with `402` / "credits depleted" | The Gemini key has no credit. Top it up or use another key. |
| `Jira returned 401` | Wrong `JIRA_EMAIL` or `JIRA_API_TOKEN`. The token belongs to the email's Atlassian account. |
| Creating a draft fails naming a required field | Your Jira project requires a field a draft cannot fill. Add a default for it in Jira. |
| `npm test` fails with an engine or `jsdom` error | Upgrade Node to 24.15 or newer. |
| `uvicorn: command not found` | Activate the backend virtualenv, then `pip install -e ".[dev]"` again. |

### No Docker?

Docker is the supported way to run it. For the tests only, `pip install -e ".[embedded-db]"` lets them start a
throwaway Postgres by themselves. To run the app you still need a PostgreSQL you can point `DATABASE_URL` at.

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
docs/              architecture.md, phases.md, ux-plan.md, sample-notes.md
.mcp.json          lets Claude Code drive the gateway at M1, M2 or M3 by hand
Dockerfile         the app image: builds the website, serves it from the API
docker-compose.yml the app and PostgreSQL together
.github/           CI, PR template, Dependabot
```

## Working on it

Read [docs/architecture.md](docs/architecture.md) first: its decisions are settled, and if you think one is
wrong, say so in a PR rather than building around it. What is planned for the interface (a Home page, Settings, a
Library) is in [docs/ux-plan.md](docs/ux-plan.md). How we work (branches, PRs, checks):
[CONTRIBUTING.md](CONTRIBUTING.md). Working agreements for people and AI assistants: [CLAUDE.md](CLAUDE.md).
Frontend details: [frontend/README.md](frontend/README.md).
