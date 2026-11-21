# api

`openapi.json` is the backend's API description, written by `backend/scripts/export_openapi.py`. A backend
test fails when it is out of date, so a route or field changed in `backend/cognipm/api/` cannot reach the
frontend unnoticed.

Do not edit it by hand. After changing the API:

```bash
cd backend
python scripts/export_openapi.py
```

## Types (Phase 6)

When `frontend/package.json` exists, add `openapi-typescript` as a dev dependency and a script that generates
`schema.d.ts` from `openapi.json`, for example:

```bash
npx openapi-typescript src/api/openapi.json -o src/api/schema.d.ts
```

Build the typed client in this folder on top of those types, so a field renamed in the backend is a compile
error here. Nothing in this folder talks to Jira or the model: it only calls the backend under `/api`.

The one non-obvious endpoint is `GET /api/runs/{id}/events`, a Server-Sent Events stream (`EventSource`). It
sends one `step` event per recorded step and an `end` event when the run is no longer running; the browser
resumes it with `Last-Event-ID` after a dropped connection.
