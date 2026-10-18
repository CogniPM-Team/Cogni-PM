# Contributing

## Layout

```
frontend/   React + TypeScript + Vite
backend/    Python + FastAPI (LangGraph orchestration, MCP gateway, pgvector RAG)
```

CI expects: `frontend/package.json` with `lint` and `build` scripts, and `backend/pyproject.toml` with a `dev` extra that includes `pytest` and `ruff`.

## Workflow

`main` is protected: no direct pushes, merge by pull request only.

```bash
git switch main && git pull
git switch -c feat/short-description
# work, commit
git push -u origin feat/short-description
```

Open a PR, fill in the template, get one approval and a green `ci`, then **Squash and merge**. The branch deletes itself.

Branch names: `feat/…`, `fix/…`, `chore/…`, `docs/…`.
Commit / PR title style: `feat: add estimate review page`, `fix: handle empty Jira scope`.

## Run the checks locally (same as CI)

```bash
# frontend
cd frontend && npm ci && npm run lint && npx tsc --noEmit && npm test --if-present && npm run build

# backend (needs Postgres with pgvector; set DATABASE_URL)
cd backend && pip install -e ".[dev]" && ruff check . && ruff format --check . && pytest -q
```

## Secrets

Never commit credentials. Copy `.env.example` to `.env` locally. Production secrets live in GitHub Environments and the hosting platforms, not in the repo.
