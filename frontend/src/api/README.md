# api

`openapi.json` is the backend's API description, written by `backend/scripts/export_openapi.py`. A backend
test fails when it is out of date, so a route or field changed in `backend/cognipm/api/` cannot reach the
frontend unnoticed.

Do not edit it by hand. After changing the API:

```bash
cd backend
python scripts/export_openapi.py
```

## Types

`schema.d.ts` is generated from `openapi.json` by `npm run gen:api` (run it from `frontend/`). Do not edit it by
hand. `types.ts` gives the generated types short names, and `client.ts` is the typed fetch wrapper, so a field
renamed in the backend is a compile error in the frontend. Commit both generated files; CI fails if
`schema.d.ts` is out of date. Nothing in this folder talks to Jira or the model: it only calls the backend
under `/api`.

The one non-obvious endpoint is `GET /api/runs/{id}/events`, a Server-Sent Events stream (`EventSource`). It
sends one `step` event per recorded step and an `end` event when the run is no longer running; the browser
resumes it with `Last-Event-ID` after a dropped connection.
