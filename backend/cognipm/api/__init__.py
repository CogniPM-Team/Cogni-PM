"""The control-plane API (FastAPI), consumed by the React frontend.

This is where a human's decisions (approve, reject, rerun, edit) are handled. An approval never goes
through the MCP gateway as a tool call: the human acting through this API is what writes to Jira, via
`gateway/apply.py`.

  main.py      the app, startup, CORS
  deps.py      per-request database connection, the Jira client, and the hooks tests override
  schemas.py   the request and response models: they become the OpenAPI schema the frontend's types come from
  launcher.py  starts an orchestrator run in the background and hands back its id straight away
  review.py    helpers for the review screen (where each cited quote sits in the input, status wording)
  routes/      runs, chat, audit and modes
"""
