# frontend/

The plan is React + TypeScript + Vite. The folder layout below is in place; the code is not.
Each empty folder holds a `.gitkeep` so git tracks it; delete that file once the folder has real content.

```
frontend/
  public/            static files served as-is (favicon, logo)
  src/
    api/             typed client for the backend API, plus the response types
    assets/          images, fonts, icons imported by code
    components/      reusable UI pieces (Layout, tables, pills, progress panel...)
    hooks/           reusable React hooks (data fetching, polling...)
    lib/             pure helpers with no React in them (formatting, grouping...), easy to unit test
    pages/           one component per route (Dashboard, Approvals, Settings...)
    styles/          global CSS and design tokens
```

## Starting it

```bash
cd frontend
npm create vite@latest . -- --template react-ts    # answer "Ignore files and continue"
npm install
```

The folders above merge with what Vite generates; move `App.tsx`, `main.tsx` etc. as you prefer.

## What CI expects

CI picks the frontend up automatically as soon as `frontend/package.json` exists, and then needs:

- a committed `package-lock.json` (CI runs `npm ci`)
- npm scripts `lint` and `build` (and `test`, which runs if present)
- `npx tsc --noEmit` to pass

At that point also uncomment the `npm` block in `.github/dependabot.yml` and delete the "Guard" steps in the
`frontend` job of `.github/workflows/ci.yml`, so a broken frontend can no longer be silently skipped.
