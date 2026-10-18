# Architecture

The decisions below are settled; they come from a working prototype. If you think one is wrong, say so in
a PR or issue rather than quietly building around it.

## What this is, and is not

CogniPM is a control plane for agentic project management **on top of Jira**. Jira owns the project data.
CogniPM owns the oversight layer: how a human delegates to an agent, at what autonomy level, and how they
review the result.

It is **not** a project-management tool (no backlog CRUD, board or gantt: Jira does that), and **not** a
general chat assistant (the one narrow exception is the read-only Co-Pilot chat, below). It does not talk to
real email, calendar or meeting systems.

## The core decision

> **Autonomy is enforced by the tool layer, not by the prompt.**

The level a task runs at decides **which MCP tools exist for that run**. We never ask a model to behave at
Level 2; we hand it a tool set that makes anything above Level 2 impossible. If you catch yourself writing
"the agent should ask permission before..." into a system prompt, stop: that belongs in the gateway.

## Autonomy levels and modes

Four levels, three user-facing modes. Code, tests and the database use `L1`..`L4`; the UI shows the mode.

| Level | Academic name | Mode shown | Tools the agent gets | Where output lands |
|---|---|---|---|---|
| L1 | AI-Assisted (Operator) | Co-Pilot | read-only | chat answer |
| L2 | Human-AI Collaborative | Super-Pilot | read + `propose_*` | staging table; human edits, then approves |
| L3 | Supervised-AI (Consultant) | Super-Pilot | read + `propose_*` | staging table, **locked**; human approves or sends back |
| L4 | Guided AI-Autonomy (Approver) | Auto-Pilot | read + `propose_*` + `commit_changes` | staging table; batch authorised, then approved |

- **L1 registers no write tools at all.** Not disabled: absent from the tool list.
- **L2 vs L3 is enforced in the UI, not the tool layer.** Same tools; L3's review screen renders values read-only. Say so honestly in code comments.
- **There is no L5** (no human in the loop), deliberately.
- Academic names are from Assalaarachchi et al., arXiv:2601.16392. In the report, always pair an L-code with its academic name.

## Guardrails sit above the levels

Server-side validators in the gateway, applied identically at every level. An agent never negotiates with a
guardrail: the call is refused and the refusal is logged. First one: **no change to the due date of a
milestone issue** (an Epic, or labelled `milestone`). Never implement a guardrail as a prompt instruction.

## How a write reaches Jira

1. An agent run calls gateway tools. `propose_*` tools only write to a **staging table**; they never touch Jira.
2. A human reviews the staged changes. For L4 they first *authorise* the whole batch, then *approve*.
3. **Approving is a human action handled by the API**, not an MCP tool call: the human is what writes to Jira
   (through the shared apply logic, which re-runs guardrails immediately before each write). An approval token
   is issued and consumed on every approval for audit parity.
4. `commit_changes` exists only at L4, only for someone driving a run by hand (e.g. from Claude Code), and only
   succeeds with an unexpired, unconsumed token that belongs to that run.

The orchestrator must call the gateway **as a real MCP client** (stdio), never by importing the gateway's
tool classes. That is what proves an agent can only do what the gateway registered for its level.

## Provenance

Jira's history attributes every change to the API user, so provenance (which agent, at what level, approved by
whom) lives in our own database as an **append-only audit log**. Enforce append-only in the database with a
trigger that rejects UPDATE, DELETE and TRUNCATE; do not rely on convention.

## Jira specifics that will bite you

- **Story points are a custom field and the id varies by site.** Never hardcode `customfield_10016`. Discover
  it once with `scripts/check_connection.py` and keep it in `.env` as `JIRA_STORY_POINTS_FIELD`.
- **The JQL search endpoint has changed.** The client uses `POST /rest/api/3/search/jql`; the older
  `GET /rest/api/3/search` is deprecated.
- **Descriptions and comments use ADF** (Atlassian Document Format), not plain text or markdown. Use the
  helpers in `gateway/jira.py`.
- **Sprints live behind the Agile API** (`/rest/agile/1.0/...`), which this project does not use.
- **Issue keys that reach a JQL string come from model output**, so validate them (`^[A-Z][A-Z0-9]+-\d+$`)
  before interpolating.
- **The API has no login yet** (one implicit reviewer). Do not expose it publicly until that changes: anyone
  who can reach it could approve a write to Jira.
