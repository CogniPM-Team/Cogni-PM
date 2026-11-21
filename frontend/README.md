# frontend/

React + TypeScript + Vite. Three screens, matching the paper's MVP: the **Agent console** (ask the Co-Pilot,
start a task), **Approvals** (review and decide on drafts), and the **Activity log**.

```
frontend/
  public/            logo and favicon
  src/
    api/             typed client for the backend; openapi.json (exported by the backend) and schema.d.ts (generated)
    components/      Layout, DraftCard, SourceText, StepTrace, ChatPanel, TaskStarter, RunProgress, TaskInspector, Pills
    hooks/           useRunEvents: follows a run's steps over Server-Sent Events
    lib/             pure helpers with no React in them: step wording, quote highlighting, CSV, formatting
    pages/           AgentConsole, Approvals, RunReview, Activity
    styles/          index.css: design tokens and components
    test/            mock API, fake EventSource, fixtures
```

## Running it

You need Node 24.15 or newer. The backend must be running (see the repo README), because the dev server proxies
`/api` to `http://localhost:8000`.

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

| Script | What it does |
|---|---|
| `npm run dev` | dev server with the API proxy |
| `npm test` | unit and component tests (Vitest, jsdom, Testing Library) |
| `npm run lint` / `npx tsc --noEmit` | ESLint and the type check |
| `npm run build` | type check, then a production build in `dist/` |
| `npm run gen:api` | regenerate `src/api/schema.d.ts` from `src/api/openapi.json` |

## When the backend API changes

The types come from the backend, so a renamed field is a compile error here instead of a silent mismatch:

```bash
cd backend && python scripts/export_openapi.py      # rewrites frontend/src/api/openapi.json
cd ../frontend && npm run gen:api                    # rewrites src/api/schema.d.ts
```

Commit both files. A backend test fails if `openapi.json` is stale, and CI fails if `schema.d.ts` is.

## Design notes worth knowing

- **Nothing is ticked by default and there is no "approve all".** Review fatigue is the main risk of human
  oversight, so the Approvals screen makes the reviewer choose each draft, shows every draft's quoted source
  highlighted in the original input, flags assumptions, and asks for one explicit confirmation naming how many
  issues will be created. The time from "ready" to the decision is recorded by the backend.
- **The wording is plain.** `lib/steps.ts` turns the run's step rows into sentences a PM would use, and
  `lib/format.ts` does the same for the activity log. Mode names are Co-Pilot, Super-Pilot, Auto-Pilot; the
  academic L-codes never appear in the UI.
- **The CSV export defuses formulas.** Log text can come from an agent or a document, so a cell that starts with
  `=`, `+`, `-` or `@` gets a leading apostrophe.
- **Auto-Pilot is shown but disabled** until Phase 8.

## What CI does

CI runs `npm ci`, lint, the type check, `npm run gen:api` followed by a check that `schema.d.ts` did not change,
the tests, and the build. Dependabot watches the npm dependencies weekly.
