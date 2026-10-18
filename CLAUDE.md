# CogniPM: working agreements

For anyone working in this repo, human or AI assistant. Read `README.md` for the overview and
`docs/architecture.md` for the design decisions. Those decisions are settled: if you think one is wrong, say
so and wait; do not quietly build around it.

## Current state

Only the Jira client (`backend/cognipm/gateway/jira.py`) is implemented. Everything else is an empty,
documented package or folder. Build the next piece; don't pre-build pieces nobody asked for.

## The rule to never break

**Autonomy is enforced by the tool layer, not the prompt.** What an agent may do is decided by which MCP tools
the gateway registers for its level. Never put "ask permission first" in a prompt; put it in the gateway.

## How to work

1. **One piece at a time.** Build exactly what was asked. If something outside it looks broken or missing,
   mention it; don't fix it in the same change.
2. **Never print to stdout in gateway or backend code.** stdio is the MCP transport; a stray `print()`
   corrupts it and the server silently fails to connect. Log to stderr.
3. **Secrets stay in `.env`.** Never hardcode a token, echo one into a log, or commit one.
4. **Add a dependency in the same change that first imports it**, and say why.
5. **Verify against real Jira, not just mocks.** Unit tests use `httpx.MockTransport`; anything that talks to
   a live site is a script in `backend/scripts/` that prints before and after state.
6. **Commit small, with messages that say why.** Squash-merge PRs; `main` is protected.
7. **If a request is ambiguous, ask one question** rather than guessing across several files.

## Definition of done

- Runs against the real Jira site (a script in `backend/scripts/` demonstrates it where relevant).
- At least one test proves the **refusal** path: the thing the system will not do.
- `ruff check`, `ruff format --check` and `pytest` pass (CI runs them).
- The author can explain every file without rereading it.
