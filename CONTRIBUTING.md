# Contributing

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
Commit / PR title style: `feat: add milestone guardrail`, `fix: handle empty Jira scope`.

## Run the checks locally (same as CI)

```bash
cd backend
pip install -e ".[dev]"
ruff check . && ruff format --check . && pytest -q
```

`ruff format .` fixes formatting for you. The frontend has no checks yet (see `frontend/README.md`).

## Rules that matter

- **Add a dependency in the same PR that first imports it**, and say why in the PR description.
- **Never print to stdout in backend code.** The MCP gateway speaks over stdio; a stray `print()` silently breaks it. Log to stderr.
- **Never commit secrets.** Copy `.env.example` to `.env` locally. Production secrets live in GitHub Environments and the hosting platforms.
- **Test the refusal paths.** For anything that gates a write (a guardrail, a missing approval token, a tool that must not exist at a level), the test that matters is the one proving the system *refuses*.
- **Tests must not need credentials or network.** Use `httpx.MockTransport` for Jira (see `backend/tests/test_jira.py`). Only `scripts/` talks to a real site.
