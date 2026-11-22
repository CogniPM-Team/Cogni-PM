# CogniPM: implementation phases

How we get from the current skeleton (only `gateway/jira.py`) to a complete product before FIT4702 starts,
using the `mcp-test` (Orbit) prototype as the template. Read with [README.md](../README.md),
[architecture.md](architecture.md) and [CLAUDE.md](../CLAUDE.md).

**MVP** = Phases 1 to 6: a PM asks for work in the agent console, the agent proposes changes in
**M2 Super-pilot**, the PM approves, edits, rejects or reruns them on the Approvals page, the approved change is
written to Jira, and every step is visible in the Activity log.

**Complete product** (before FIT4702) = MVP plus Phases 7 to 10: task controls, M3 Auto-pilot, multi-agent
orchestration and RAG, and the work needed to run the real-user evaluation.

Every phase ends with the repo's definition of done: it runs against the real Jira site (a script in
`backend/scripts/` prints before and after), at least one test proves the **refusal** path, `ruff` and `pytest`
pass in CI, and the author can explain every file.

Every phase also ends with a **suggested commit message**. We squash-merge, so use it as the PR title (first
line) and PR description (the rest). Style is Conventional Commits (`feat`, `fix`, `docs`, `chore`, `test`) with
an optional scope. The subject says what changed in under about 70 characters; the body says *why*. A phase
that lands as several PRs gets one subject per PR, as in Phase 6.

---

## Phase 0: decisions (settled 13 Nov 2026)

These are small, but each one changes code in several later phases. All five are now decided.

| # | Decision | Outcome |
|---|---|---|
| D1 | **Mode names in code.** `docs/architecture.md` and `mcp-test` use L1 to L4 internally; the Design canvas still shows L1 to L4 as Consultant / Co-worker / Committer / Super-pilot. The agreed product names are **M1 Co-pilot, M2 Super-pilot, M3 Auto-pilot**. | **Accepted.** Key the gateway, database and tests on `M1`/`M2`/`M3` from the start (there is no legacy data yet). Keep the Assalaarachchi et al. academic names as a documented mapping for the paper. Update `docs/architecture.md` in the same PR as Phase 2. |
| D2 | **What happens to the old L3 "locked review" variant.** M2 is approve / edit / reject / rerun, which is the old L2. | **Accepted.** Drop the locked variant. If the study wants it later, it is a UI flag on M2, not a separate mode. |
| D3 | **MVP task type(s).** Only story-point re-estimation is real in `mcp-test`; the submitted paper commits the MVP to **P1 Product Backlog Drafting** and **P2 Task Breakdown/Creation**. | **P1 + P2 are the MVP**, matching the paper. P1: the agent drafts user stories and acceptance criteria from requirements and meeting notes. P2: the agent breaks an approved story into tasks and sub-tasks. Both only *create* new Jira issues, after approval. Story-point re-estimation (already built in `mcp-test`) moves to Phase 8 as the first M3 automation (see Phase 8). See "What D3 changed" below. |
| D4 | **Database.** `mcp-test` uses SQLite; the repo plans PostgreSQL + pgvector. | **Accepted.** PostgreSQL from Phase 2 (`pgvector/pgvector:pg16` in Docker locally and as a CI service), plain numbered SQL migrations like `mcp-test/db/migrations`. pgvector is only used from Phase 9. |
| D5 | **Who builds what.** Four people. | **Accepted.** Backend critical path (Phases 1 to 5) is sequential. Once the Phase 5 API contract is drafted, the frontend scaffold (6a) can start in parallel against mocked responses. |

### What D3 changed

`mcp-test` proposes a **new value for an existing issue** (a story-point number). P1/P2 propose **new issues**.
That is a different shape of change, and it ripples through the phases below:

- **Nothing to diff.** A create has no "current value", so review shows the full draft (title, description,
  acceptance criteria, parent, sources) instead of current-versus-proposed.
- **Drafts are structured, not a scalar.** A staged change holds a JSON payload (and an edited payload) instead
  of `old_value`/`new_value`/`edited_value` text columns.
- **Creates are riskier in different ways:** duplicates, wrong parent, runaway counts, and a half-finished batch
  if Jira fails partway. Guardrails (Phase 4) and the approve path (Phase 5) are written for that.
- **New agent input.** The agent needs requirements and meeting notes as input, with each draft citing the
  passage it came from (the paper requires traceability to source).
- **Capture the study metrics now.** Edit rate, rejection rate, rerun count, time to decision and tokens per run
  are stored from the first run, because they cannot be reconstructed later.

**Suggested commit message**

```
docs: record Phase 0 decisions and rework the phases for a P1/P2 MVP

Accept D1, D2, D4 and D5. D3 makes P1 backlog drafting and P2 task
breakdown the MVP, as the paper commits to, instead of story-point
re-estimation. Those tasks create new Jira issues rather than change a
value, so update phases 1-6 and 9 for drafts, cited sources, create-only
guardrails and partial approval.
```

---

## Phase 1: Jira integration (template: `mcp-test/gateway/jira.py`)

`backend/cognipm/gateway/jira.py` is already ported (REST v3, Basic auth, `POST /search/jql`, ADF helpers,
`search_issues_for_analytics`). This phase makes it production-ready for what the MVP needs.

- ~~Run `scripts/check_connection.py`; set `JIRA_STORY_POINTS_FIELD` in `.env`.~~ **Done 13 Nov**: `.env` is
  configured from `mcp-test`, the connection works (project `MCP`), and the field is `customfield_10016`. Note
  the site has a second story-point field (`customfield_10038` "Story Points"); P1/P2 don't write points, so
  this only matters when estimation returns in Phase 8 (the story-point automation).
- ~~Add `validate_issue_key()` and use it wherever a key reaches JQL or a URL path.~~ **Built.** Uses
  `^[A-Z][A-Z0-9_]+-\d+$` (Jira project keys may contain `_`, which the first draft of the regex refused) with
  `fullmatch`, so a trailing newline is rejected too. Applied in `get_issue`, `update_issue_fields`,
  `add_comment`, `delete_issue`, `get_project` and for a sub-task's parent. `key_in_jql()` is the one safe way to
  put keys into JQL.
- ~~**Create path for P1/P2**~~ **Built:** `list_issue_types()` reads the project's types (ids differ per site, so
  `issue_type("Story")` looks one up by name and caches it), and `create_issue()` creates a Story, Task or
  Sub-task. It checks everything (summary present and at most 255 characters, a sub-task has a parent, keys are
  valid) **before** any request is made, and returns a `CreatedIssue` with the key and a browse link.
  - Confirmed on the real site: `Story` 10005, `Task` 10008, and the sub-task type is named **`Sub-task`** (10006).
  - **Decided: acceptance criteria live in the description**, as an "Acceptance criteria" heading plus a bullet
    list (`draft_to_adf`), so nothing depends on a site-specific custom field.
  - A Jira 4xx is raised, never swallowed; `describe_error()` turns it into a readable message such as
    `Jira returned 400: description: ...`.
- ~~Add `add_comment(issue_key, text)`~~ **Built** (sent as ADF), for the optional provenance comment mirrored
  into Jira after an approved write.
- ~~Add `scripts/verify_write.py`~~ **Built and run live (13 Nov).** It needs `--confirm`, creates one sandbox
  Story and one Sub-task labelled `cognipm-sandbox`, comments, reads both back, then cleans up. `delete_issue()`
  and `close_issue()` refuse any issue without that label, so they cannot touch real work. It uses two issue
  numbers per run in `MCP` that Jira never reuses.
- **Finding: the API user cannot delete issues** here (403, "You do not have permission to delete issues").
  Cleanup therefore falls back to `close_issue()`, which finds the transition that ends in a done status and
  reads the status back. The sandbox issues MCP-11 to MCP-14 stay in `MCP` as Done. This is why Phase 8's undo
  of a created issue closes by default.
- ~~Tests (`httpx.MockTransport`)~~ **Built** (48 passing): malformed and injection-style keys are refused before
  any request; a bad summary or an orphan sub-task never reaches Jira; delete and close refuse unlabelled
  issues; close reports a workflow with no done transition.

**Done when:** the live script shows create, read-back and cleanup on the real sandbox, and the refusal tests
pass. **Met.** (The last run printed PASS. After it, the script's read-back check was tightened, because JQL
search lags a moment behind writes; that edit has not been re-run live, to avoid creating two more issues.)

**Suggested commit message**

```
feat(jira): add issue creation, key validation and comments

Add list_issue_types, create_issue (story, task, sub-task with a parent),
add_comment and validate_issue_key. Issue keys reach JQL and URL paths and
come from model output, so they are validated before any request is made.
Add close_issue for sandbox issues, used when the API user may not delete.
scripts/verify_write.py creates a sandbox story and sub-task on the real
site, then deletes or closes them, to prove the write path before the
gateway exists.
```

---

## Phase 2: database and MCP gateway (template: `mcp-test/gateway/server.py`, `apply.py`, `db/`)

The heart of the project: autonomy enforced by which tools exist.

**Database (`backend/cognipm/db/`)**
- One Postgres migration based on `mcp-test` migrations 0001 to 0004: `runs`, `approval_tokens`, `audit_log`,
  `chat_sessions`, `chat_messages`. **`staged_changes` is redesigned for creates (D3):** `kind`
  (`backlog_item` | `task` | `subtask`), `payload` JSONB (summary, description, acceptance criteria, issue type,
  parent key, labels), `edited_payload` JSONB, `sources` JSONB (the input passages the draft cites),
  `reasoning`, `assumptions`, `action_class`, `status` (`proposed` | `applied` | `failed`), `created_issue_key`,
  `applied_at`. A P2 draft points at its P1 parent (an existing key, or another staged draft in the same run).
- `runs` also stores what the study needs: `model`, `input_tokens`, `output_tokens`, `rerun_of` (so reruns
  chain) and `decided_at`. `audit_log` records edits as a before/after diff.
- `audit_log` append-only **enforced by a trigger** that rejects UPDATE, DELETE and TRUNCATE (an improvement on
  `mcp-test`, which relied on convention). Test: an UPDATE on `audit_log` raises.
- `log_audit()` port; add `psycopg` to `pyproject.toml` in this PR; add the Postgres service to CI.

**Gateway (`backend/cognipm/gateway/server.py`, `apply.py`)**
- `GatewayTools` with injectable Jira client and DB connection, as in `mcp-test`.
- One table is the whole enforcement mechanism:

  | Mode | Tools registered |
  |---|---|
  | M1 Co-pilot | `search_issues`, `get_issue` |
  | M2 Super-pilot | read + `start_run`, `propose_backlog_item`, `propose_task_breakdown`, `finish_run` |
  | M3 Auto-pilot | M2 + `commit_changes` (grant-gated; the automation allowlist narrows this per run in Phase 8) |

- `propose_*` writes only to `staged_changes`; it never creates a Jira issue. Each proposal needs reasoning of at
  least 20 characters, non-empty assumptions (or `NA`), and at least one cited source passage, as the paper
  requires traceability to the input.
- `apply.py`: the one place a staged change becomes a Jira write; creates the issue from `edited_payload` if set,
  else `payload`. It creates **parents before children**, records `created_issue_key` as it goes, and on a
  Jira failure stops and reports exactly which items were and were not created (never a silent half-batch). It
  calls a **guardrail chain** (empty except for the milestone rule ported as-is) so Phase 4 adds rules without
  restructuring.
- Mode read from `COGNIPM_MODE`, agent identity from `COGNIPM_AGENT`; no stdout anywhere; add `.mcp.json` so
  Claude Code can drive the gateway by hand.
- Tests to port: `test_server_tool_registration` (M1 has **no** propose tools: absent, not disabled),
  `test_propose_estimate_change` becomes `test_propose_backlog_item` (no Jira call at propose time),
  `test_commit_changes` (refused without a valid token: missing, wrong run, expired, consumed). New: a
  proposal with no cited source is refused; `apply` creates a parent before its sub-task.

**Done when:** `claude mcp list` shows the gateway connected, `/mcp` lists the right tools per mode, and a
scripted M2 run from Claude Code stages a draft story without touching Jira.

**Status (13 Nov): built.** 104 tests pass against a real Postgres, ruff is clean, and
`scripts/demo_stage.py` ran against the real `MCP` site: the gateway, launched as an MCP client over stdio,
offered M1 two read tools, M2 six tools without `commit_changes`, and M3 seven; an M2 run staged a draft and
the project still had 14 issues before and after. Not yet checked: `claude mcp list` (needs a reachable
`DATABASE_URL`, because every mode connects to the database at startup). Decisions taken while building:
- `sources` is a list of quoted passages (strings); `propose_task_breakdown` makes `subtask` drafts only (the
  `task` kind exists in the schema for later); a sub-task's parent is `parent_key` **or** `parent_change_id`.
- `staged_changes.status` also has `rejected` (the PM unticks or rejects a draft); `runs.status` also has
  `failed`. A failed `commit_changes` leaves the token unconsumed so a retry creates only what is left.
- The milestone rule is ported but **not in the chain**: P1/P2 set no dates, so it has nothing to check until a
  tool can change a due date. The chain (`GUARDRAILS`) is empty and logs refusals by guardrail name.
- `issue_approval_token()` lives in `gateway/server.py` as a plain function, not a tool, so an agent can never
  mint one. Phase 5's approve route will call it.
- Added the optional `embedded-db` extra (`pgserver`) so the database tests run without Docker.

**Suggested commit message**

```
feat(gateway): add Postgres schema and the mode-scoped MCP gateway

Add the migration (runs, staged_changes with JSON draft payloads,
approval_tokens, and an audit_log that a trigger makes append-only) and
GatewayTools with one TOOLS_BY_MODE table: M1 reads only, M2 adds
propose_backlog_item, propose_task_breakdown and finish_run, M3 adds
commit_changes. Propose tools stage drafts and never call Jira, and each
needs a cited source. Key everything on M1/M2/M3 and update
docs/architecture.md to match.
```

---

## Phase 3: orchestrator (template: `mcp-test/orchestrator/`)

- Port `mcp_bridge.py` (MCP tool schema to Gemini function declarations, result unwrapping) and the agent loop
  from `agent.py` / `chat.py`, rebuilt as a **LangGraph** graph as the repo intends. The reason to use LangGraph
  rather than the prototype's plain loop is checkpointed state, which Phase 7 needs for pause, stop, resume and
  mid-task mode change.
- The orchestrator spawns the gateway as a **real MCP client over stdio** at the run's mode, never importing
  `GatewayTools`. Two entry points:
  - `run_chat_turn` (M1): read-only Q&A, the conversational part of the agent console.
  - `run_task` (M2): one-shot task run that ends in `finish_run` and status `awaiting_review`. Two task
    prompts: **P1** (requirements + meeting notes in, draft stories with acceptance criteria out) and **P2** (an
    approved story in, tasks and sub-tasks out). Use Gemini **structured output** against a Pydantic schema so a
    malformed draft is rejected before it is staged. Input text comes from the PM pasting or uploading it; keep
    the original passages so each draft can cite them.
- Run states for the MVP: `queued → analysing → generating → awaiting_review → applied | rejected`, plus
  `failed`. (The full state machine from the requirements evaluation arrives in Phase 7.)
- Persist each step (model call, tool call, result) to a `run_steps` table instead of `mcp-test`'s in-memory job
  dict, so the console can stream them and the activity log can replay them after a restart.
- Keep `MAX_TOOL_CALLS`, the stall nudge, and the lesson from `mcp-test`: raise errors after the MCP client
  context exits, or they arrive wrapped in an exception group.
- Tests: scripted fake Gemini against an in-process gateway (as `mcp-test/tests/test_orchestrator.py`); refusal:
  an M1 run cannot open a run because `start_run` does not exist for it.

**Done when:** `scripts/demo_run.py` runs a real Gemini M2 P1 draft over a short sample requirements document
(then P2 on one approved story) and prints the staged drafts with their cited sources, with Jira unchanged. Use
only synthetic or anonymised input: the paper's Privacy Act row says project data sent to the model is sandboxed.

**Status (20 Nov): built and run live.** 125 tests pass against a real Postgres and ruff is clean. The first live
attempt on 13 Nov failed with HTTP 402 (prepaid credits depleted); the error was reported and Jira was unchanged.
After a top-up, `python scripts/demo_run.py` passed: P1 over the synthetic planning notes staged two drafts
(password reset by email; monthly CSV export of paid and overdue invoices), each with acceptance criteria,
assumptions and verbatim quotes, and correctly left out the dark theme nobody committed to. P2 on MCP-4 staged
three sub-tasks. The project had 14 issues before and after, and `run_steps` replayed each run. Token use was
593 in / 373 out for P1 and 183 in / 261 out for P2. Observation: P2 sub-tasks on a one-line story all cite the
same sentence, so P2 quality depends on how much the story says. Decisions taken while building:
- **Tasks are a fixed graph, not a model-driven tool loop.** `open_run -> analyse -> generate -> verify ->
  stage`. Gemini has no tools in P1/P2; it returns JSON checked against a Pydantic schema (`schemas.py`), and
  this code calls the gateway (`start_run`, `propose_*`, `finish_run`) over MCP. The mode still decides what is
  possible: a run at M1 cannot begin because `start_run` does not exist. The model-driven tool loop is kept only
  for the M1 chat (`chat.py`). The prototype's stall nudge was dropped because nothing needs the model to call
  `finish_run` any more.
- **Quotes are checked, not trusted.** Each cited passage must appear in the input (ignoring case, whitespace and
  typographic quotes). A draft with no verifiable quote is dropped; if nothing survives the model gets one retry
  with the problems listed; after that the run fails and stages nothing.
- **Run states** are recorded as `run_steps` rows (`analysing`, `generating`, `verifying`, `staging`; migration
  0002) rather than new `runs.status` values. `queued` belongs to the API in Phase 5.
- **Fix to Phase 2:** the MCP server hides the text of any exception a tool raises, so a refusal ("reasoning must
  be at least 20 characters") never reached the caller. The gateway now turns its deliberate refusals into
  `ToolError` so the agent can see why, while real crashes stay masked.
- New dependencies: `google-genai`, `langgraph`, and `pytest-asyncio` (dev).

**Suggested commit message**

```
feat(orchestrator): run P1 and P2 as LangGraph graphs over the gateway

Port the MCP bridge and rebuild the agent loop as a LangGraph graph that
calls the gateway as a real MCP client over stdio, so a run can only use
the tools registered for its mode. Add run_chat_turn (M1) and run_task
(M2) with structured Gemini output, cited source passages, and run_steps
persisted to the database so progress survives a restart.
```

---

## Phase 4: guardrails (template: `mcp-test/gateway/guardrails.py`)

Server-side validators applied identically in every mode, run at propose time **and** again in `apply.py`
immediately before each write. Every refusal is logged with the guardrail's name and returned to the agent as a
structured error.

- `no_milestone_date_change` (port): Epic or `milestone` label. P1/P2 don't set dates, so this mainly guards a
  draft that tries to.
- `in_project_scope`: every created issue must target the configured project key.
- `create_only`: M2 may create new issues; it may never update, transition, link or delete an existing one.
  (Phase 8 widens this for M3 only, per automation, through `update_allowed_fields`.)
- `valid_parent`: a Sub-task's parent must exist in Jira or be an earlier item in the same approved batch; a
  Sub-task may not be the parent of anything.
- `no_duplicate`: refuse a draft whose summary matches an existing open issue in the project (case-insensitive;
  start simple, tune on real runs).
- `max_items_per_run`: a cap on how many issues one run may create, so a bad run cannot flood the backlog.
- `required_fields`: non-empty summary; for stories, a non-empty acceptance-criteria section.
- **Action classes** (from the requirements evaluation): every staged change carries `read`, `internal`,
  `structural` or `external`. Creating issues is `structural`. `external` is always gated, in every mode
  including M3; this is the hard floor Phase 8 relies on.
- Approval tokens expire; an expired or stale approval never executes.
- `required_fields` also asks Jira which fields the project requires when creating each issue type, and refuses
  a draft that cannot satisfy them, with a clear message (H5). Instructions found inside the input text are never
  acted on, and `max_items_per_run` limits the damage if a document tries to flood the backlog (H8).
- Tests: one refusal test per guardrail, run at M1, M2 and M3.

**Status (20 Nov): built and run live.** 167 tests pass against a real Postgres and ruff is clean.
`scripts/demo_guardrails.py` ran against the real `MCP` site through the gateway's propose tools at M2: a
sub-task under a parent in another project (`in_project_scope`), a backlog item titled like open issue MCP-4
(`no_duplicate`), a sub-task under a parent that does not exist (`valid_parent`), and a Story with no acceptance
criteria (`required_fields`) were each refused with the guardrail's name in the audit log, a well-formed draft
passed the whole chain including Jira's own create metadata, and the project had 14 issues before and after.
Decisions taken while building:
- **Nine rules, cheapest first:** `required_fields`, `create_only`, `external_is_gated`, `max_items_per_run`,
  `no_milestone_date_change`, `in_project_scope`, then the three that read Jira: `valid_parent`, `no_duplicate`,
  `jira_required_fields`. A draft refused locally costs no Jira request. Each guardrail now receives a
  `DraftContext` (Jira client, database, run, mode, stage, whether the call is automatic).
- **`required_fields` is two rules.** The local one (title, and acceptance criteria for a Story) is
  `required_fields`; the question to Jira ("which fields does this project require?", answered by the create
  metadata, which I confirmed on the real site) is `jira_required_fields`, so a refusal names which one fired.
- **Propose now reads Jira.** The rules need Jira's state, so a proposal makes a few read requests (an open-issue
  search, the parent, the create metadata). It still never writes; the tests now assert "no create request"
  rather than "no request".
- **`no_duplicate` is deliberately simple:** exact title (ignoring case and spacing) against the 100 most
  recently created open issues, plus other drafts in the same run. No model text is placed in a JQL string.
- **`max_items_per_run`** defaults to 20 (`COGNIPM_MAX_ITEMS_PER_RUN`). At propose time it counts drafts, at apply
  time it counts issues actually created.
- **`external_is_gated`:** an `external` draft is refused when `commit_changes` (no person approving) tries to
  apply it, and allowed when a human approves through the API. Nothing creates an `external` draft yet.
- **Stale approvals:** `commit_changes` refuses a token if any draft was staged after the token was issued.
  Token expiry was already enforced in Phase 2.
- The ported milestone rule for changing an *existing* issue's due date (`check_no_milestone_date_change`) is
  kept for Phase 8 and is not in the chain; `no_milestone_date_change` in the chain stops a draft that carries a
  date on an Epic or a `milestone`-labelled issue.

**Done when:** a live script tries an out-of-project create, a duplicate, and an orphan sub-task and shows each
refused and logged, with Jira unchanged.

**Suggested commit message**

```
feat(guardrails): add create-time guardrail chain and action classes

Add in_project_scope, create_only, valid_parent, no_duplicate,
max_items_per_run and required_fields. They run when a draft is proposed
and again immediately before each Jira write, so a stale approval cannot
get around them. Every refusal is logged with the guardrail's name.
Tag each staged change with an action class; external is always gated.
```

---

## Phase 5: control-plane API (FastAPI, `backend/cognipm/api/`)

The human's decisions live here, not in the gateway: approving is what writes to Jira.

- `POST /chat` (M1 turn), `POST /runs` (start an M2 task: `task` = `p1` or `p2`, plus the input text or the
  approved story key), `GET /runs`, `GET /runs/{id}` (the staged drafts with their sources; for P2 also the
  parent story), `GET /runs/{id}/events` (Server-Sent Events of `run_steps` for the console).
- `PATCH /changes/{id}` (edit a draft's fields; stored as `edited_payload`), `POST /runs/{id}/approve` (a PM may
  approve a subset: unticked drafts are dropped, not created), `POST /runs/{id}/reject` (with a note),
  `POST /runs/{id}/rerun` (regenerate with the PM's note as extra instruction; the new run records `rerun_of`).
- `GET /audit` with filters (all, changed Jira, needs you, rejected, advice only), `GET /modes` generated from the
  tool table so the UI cannot drift from what the gateway enforces.
- Approve goes through `apply.py` only, issues and consumes a token for audit parity, and is idempotent.
- **Duplicate-create safety (see "Hardening and gaps", H1):** `apply.py` stamps every issue it creates with its
  draft id and checks for that stamp before creating, so a retry after a crash never makes a second issue.
- **Provenance in Jira (H2):** every created issue gets the label `cognipm-drafted` and a comment naming the run,
  the mode, and who approved (`add_comment` already exists).
- Export the OpenAPI schema and generate TypeScript types for `frontend/src/api/`.
- Tests: approving twice is refused (no duplicate issues); reject never writes; editing an applied change is
  refused; a Jira failure halfway through a batch reports exactly which items were created and which were not.

**Status (20 Nov): built and run live.** 213 tests pass against a real Postgres and
ruff is clean. Every route is tested end to end through the real app with a scripted model and a fake Jira,
including the refusals: approving twice, approving a sub-task without its parent, editing a created draft, and
Jira failing halfway (the response lists exactly what was and was not created, and approving again creates only
the rest). `scripts/demo_flow.py --confirm` drives the whole flow over HTTP against the real site; it creates one
issue and Gemini calls. It passed on the real `MCP` site: the Co-Pilot answered a question; a P1 run over
synthetic notes produced two drafts with their quotes located in the input; the PM edit and a one-draft approval
created MCP-15 with the PM's wording, the `cognipm-drafted` label and the draft-id stamp, while the other draft
was dropped and not created; approving again returned 409; the script then closed MCP-15 (the API user cannot
delete). Two things the run showed: the Co-Pilot first sent an unbounded JQL query, Jira refused it with a clear
message, and the model read that message and corrected itself (the refusal-text fix from Phase 3 working as
intended; a line in the chat prompt saying JQL must be restricted, e.g. `project = ...`, would save the retry);
and the model chose its own labels (`authentication`, `security`, `support`) that were not in the notes, so
decide whether drafts should be allowed to carry labels at all. What was built:
- **Routes** (all under `/api`): `POST /runs`, `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/events` (SSE with
  `Last-Event-ID` resume), `PATCH /changes/{id}`, `POST /runs/{id}/approve|reject|rerun`, `POST /chat`,
  `GET /audit?filter=`, `GET /modes`, `GET /health`. Responses are typed Pydantic models, so the OpenAPI schema
  carries real types.
- **Starting a run returns at once.** `POST /runs` answers 202 with the run id as soon as the gateway has opened
  the run (a new `on_run_started` hook in the orchestrator), and the run continues in the background.
- **Review support:** each draft's cited quotes come back with their position in the original input
  (`sources[].start/end`) so the UI can highlight them (H6); the run stores `input_text`, `instructions`,
  `story_key`, and `ready_at`, so a rerun starts from the same input and `seconds_to_decision` can be reported
  (migration `0003_run_input.sql`). `input_text` is project data: the retention policy in H4 applies to it.
- **H1, duplicate-create safety: done.** Every issue is stamped with the label `cognipm-draft-<draft id>`, and
  before creating, Jira is searched for that stamp; a draft whose issue already exists is adopted, not created
  again (audited as `recovered`). Known limit: Jira's search index lags a moment behind writes, so a retry in
  the first second or two after a crash can miss it.
- **H2, provenance in Jira: done.** Every created issue gets the label `cognipm-drafted` and a comment naming the
  run, the mode and the approver (a failed comment is audited, not fatal).
- **H7, durability: partly done.** A model call is retried up to twice on 429 and 5xx with a pause (not on 402 or
  400) and each retry shows in the step trace; a run that was `running` when the server stopped is marked `failed`
  at startup instead of staying `running` forever. Not done: a persisted queue, so a restart still abandons a run
  in flight (it can be rerun). Fine for one API process; revisit before more than one.
- **Concurrency:** approve, reject and rerun take a per-run database lock, so two clicks or two tabs cannot both
  create the issues.
- **Approve semantics:** `change_ids` ticks a subset and any pending draft left out is dropped (`rejected`); a
  sub-task whose parent is unticked is refused before anything is written. A run that `failed` part-way can be
  approved again.
- **Rerun** starts the new run first and rejects the old one only once the new run exists, so a rerun that cannot
  start leaves the original alone.
- **Types for the frontend:** `frontend/src/api/openapi.json` is exported by `scripts/export_openapi.py`, and a
  test fails if it is out of date. Generating the TypeScript types waits for the Phase 6 scaffold, where
  `openapi-typescript` becomes a dev dependency. New dependencies: `fastapi`, `uvicorn`.
- Still open for Phase 7: login (H3). Until then do not expose this API publicly.

**Done when:** the whole MVP flow can be driven with `curl` against the real site.

**Suggested commit message**

```
feat(api): add the control-plane API for runs, review and audit

Add endpoints to start a P1/P2 run, stream its steps, edit a draft,
approve a subset, reject, and rerun, plus the audit log and a modes
endpoint generated from the gateway's tool table. Approve goes through
apply.py only, is idempotent, and reports exactly which issues were
created if Jira fails partway. Export the OpenAPI schema and generate
TypeScript types for the frontend.
```

---

## Phase 6: frontend (React + TypeScript + Vite)

The UI prototype is the Design canvas (Agent console, Approvals and Activity log screens). Use M1/M2/M3 names
in the UI, not the canvas's L1 to L4 labels.

**6a. Scaffold** (can start in parallel once the Phase 5 contract is drafted)
- Vite + React + TS per `frontend/README.md`; router; design tokens from the canvas; app shell with sidebar
  (Agent console, Approvals with a pending badge, Activity log) and top bar.
- Typed API client from the generated types. Enable the CI `frontend` job (remove the guard steps) and npm
  Dependabot.

**6b. Agent console** (the chat interface)
- Chat thread with the orchestrator; a mode selector (M1 for questions, M2 for tasks; M3 shown but disabled until
  Phase 8). Choosing M2 offers the two MVP tasks: **Draft backlog (P1)**, with a place to paste or upload
  requirements and meeting notes, and **Break down a story (P2)**, with a picker for an approved story.
- Live step trace streamed from `/runs/{id}/events`, in plain language as `mcp-test/app/jobs.py` does.
- When a run finishes, an inline proposal card (the draft's title, why, sources) with a link to review it in
  Approvals.
- Task inspector panel: status, mode, work so far (completed, pending, awaiting approval).
- "Agents can make mistakes" note next to AI output.

**6c. Approvals**
- Pending runs first, oldest first. Detail pane: action class, mode, rationale, assumptions, the full draft
  (there is no current value to diff against), the cited source passages beside it, expiry.
- **Designed against review fatigue (H6):** each draft's cited quote is highlighted inside the original input,
  assumptions are flagged, nothing is ticked by default (no "approve all" shortcut), and time to decision is
  recorded per run. This screen is a research instrument as much as a feature.
- A checkbox per draft so the PM can approve only some; editable fields (title, description, acceptance
  criteria, parent) with the edit shown as a before/after in the audit log.
- Actions: **Approve and execute**, **Edit before approving**, **Regenerate** (with a note), **Reject** (with a
  note saved as feedback). Header copy: nothing here has touched Jira yet. After approval, show the created issue
  keys as links into Jira.

**6d. Activity log**
- Append-only table grouped by run: time, actor (human or which agent), action, mode at the time, outcome;
  filters as in Phase 5; detail pane with approver, rationale and sources; CSV export (needed for the evaluation).

**Status (21 Nov): built.** All four sub-phases are in. 30 frontend tests, the type check, lint and the production
build pass, and the backend still passes its 214 tests. I looked at the real screens in a browser against the
real API with seeded data (never confirming an approval, since that API was wired to your live Jira): the review
page with highlighted quotes, ticking a draft and the confirmation naming how many issues it creates, the
approvals queue, the activity log and the console. What was built:
- **6a Scaffold:** Vite, React 19, TypeScript, React Router, ESLint, Vitest. The API client's types are generated
  from the backend's OpenAPI schema (`npm run gen:api`), so a renamed field is a compile error. CI's `frontend`
  job is on for real (the guard steps are gone, and it checks `schema.d.ts` is current) and Dependabot watches
  npm. CI now uses Node 24, because `jsdom` needs 22.22+ or 24.15+. TypeScript is pinned to 5.9 because
  `openapi-typescript` does not support 6.
- **6b Agent console:** a mode selector (Co-Pilot, Super-Pilot, and Auto-Pilot shown but disabled); a chat that
  keeps its conversation; a task starter for P1 (paste text or load a `.txt`/`.md` file) and P2 (a picker of open
  stories); a live step trace over Server-Sent Events in plain sentences; an inline summary with a link to the
  review when drafts are ready; and the task inspector (status, work so far, waiting for you, created in Jira,
  model use). Backend additions to support it: `GET /api/stories` and `GET /api/project`.
- **6c Approvals:** the queue (waiting first, oldest first, then earlier runs) and the review page. Built against
  review fatigue (H6): nothing ticked by default, no approve-all, each draft's quotes highlighted in the original
  input (hovering a draft strengthens its quotes), assumptions flagged, one explicit confirmation that names how
  many issues will be created and how many are left out, then links to the created issues. Per-draft editing
  (title, description, criteria, labels, type) with the agent's original shown beside it; Reject and Regenerate
  each take a note; a Jira failure part-way shows exactly what was and was not created.
- **6d Activity log:** filters matching the API, plain-word actions, detail and before/after on request, a
  group-by-run view, and a CSV export that defuses spreadsheet formulas.
- **Not done:** the typed client has no login (H3, Phase 7); the editor has no parent picker, because a draft's
  parent is fixed by the run; Auto-Pilot is disabled until Phase 8; accessibility was designed in (labels, roles,
  focus, reduced motion) but not audited with a screen reader.

**Chat sessions (added 21 Nov, branch `feature/chat-sessions`).** The Co-Pilot's conversations are kept and
organised like a chat app's: a **Chats** list in the sidebar with **+ New chat**, reopening any earlier chat at its
own address (`/console/<id>`) with its full history (and "Read Jira N times"), **rename**, **delete**, and
**folders** (create, rename, delete, move a chat in or out from its menu). Decisions:
- Scope is Co-Pilot chats only. Task runs already have their history in Approvals and the Activity log.
- A chat is created when the first answer comes back (so a failed first question leaves nothing behind) and is
  titled from that first question; renaming does not reorder the list, and the list is ordered by last use.
- Deleting a chat deletes its messages for good (also the way a user gets their own words out of the system, H4);
  the Activity log keeps only content-free rows ("Answered a question", "Deleted a chat"). Deleting a folder keeps
  its chats and moves them out of it.
- The mode is part of the address (`/console?mode=M2`), so "New chat" is always the Co-Pilot.
- Migrations `0004_chat_organisation.sql` (folders, titles, last-used time, reads per answer) and
  `0005_backfill_chat_titles.sql` (titles earlier chats from their first question and removes the empty chats a
  failed first question used to leave behind).
- API: `GET/PATCH/DELETE /api/chat/sessions[/id]`, `POST/PATCH/DELETE /api/chat/folders[/id]`; `POST /api/chat`
  now returns the chat's `title`. 232 backend and 52 frontend tests pass.
- The chat list is a second panel inside the Agent console (not the main sidebar). Drag a chat onto a folder to put it
  there, or onto the area below the folders to take it out; the menu's "Move to" is the keyboard route.
- The shell is exactly the window tall: sidebar, top bar and footer stay put, pages scroll inside, and the console's
  chat list and conversation stretch to full height with the message box pinned at the bottom.
- The console's flow (21 Nov): the mode switch is a compact segmented control with a one-line description, and both
  modes stay mounted (the other is hidden), so hopping to Super-Pilot and back keeps your open chat, an unsent
  question and the runs you started; the pane that appears fades up (and does not move for people who prefer
  reduced motion). The Co-Pilot is a centred, readable column with an empty state and suggested questions, "You" and
  "Co-Pilot" labels, and a question box that grows as you type and is pinned at the bottom (Enter sends). The Task
  inspector appears only in Super-Pilot, which gives the chat the room.
- One constant frame (21 Nov, second pass): the console is always a history list on the left and the work area
  beside it, so switching mode never moves the layout. The Co-Pilot's list is its chats; the Super-Pilot's is its
  **Tasks** (recent runs with status, the ones waiting for you first, each opening its review). The Task inspector
  is now a slim summary strip above the run (it appears once a task exists) instead of a third column that popped
  in and out. Both modes use the same centred reading column.
- Full-space layout (21 Nov, third pass): the console is no longer capped to a reading width. The Co-Pilot's
  conversation and question box span the whole work area (with the mode tabs and description on one line to save
  height). Super-Pilot is two panes, each as tall as the window: the task form on the left (the text box stretches
  to fill the height) and live progress and results on the right (a placeholder until a task starts). Below about
  1250px the two panes stack and the page scrolls. Other pages keep their 1280px cap.
- Not done: search across chats and nested folders.

**One-command run (22 Nov).** `docker compose up --build` starts the whole product: the API serves the built website
(one address, `http://localhost:8000`) beside a PostgreSQL container. The `Dockerfile` builds the frontend in a Node
stage, then installs the backend in a Python stage with the website next to it; secrets are read from `.env` at run
time and are never in the image (CI checks there is no `.env` in it). The API serves `index.html` for every non-API
path, so a deep link or reload works, and refuses to serve any file outside the website folder. Verified: both
containers healthy, the site and a deep link load, an unknown `/api` path is a JSON 404, a real Jira read works, and the
MCP gateway runs as a subprocess inside the container (M1, M2, M3 tool sets over stdio). Ports bind to 127.0.0.1 only
because there is no login. The database is published on 5433 (not 5432) so it does not collide with a PostgreSQL on
the host.

**Done when (MVP complete):** a PM can paste requirements in the console, review and approve the drafted stories
in Approvals, break one down into tasks, see the created issues in Jira, and trace every step in the Activity
log, with a recorded end-to-end demo. This is the paper's "end of November" MVP: LLM integration, approval
workflow, audit logging, and Jira writes through the MCP gateway.

**Suggested commit messages** (one per sub-phase, each its own PR)

```
chore(frontend): scaffold the Vite React TypeScript app and enable CI
```

```
feat(frontend): add the agent console with M1 chat and M2 task start

Chat thread, mode selector, a P1 input box for requirements and meeting
notes, a P2 story picker, a live step trace, and the task inspector.
```

```
feat(frontend): add Approvals with edit, regenerate and reject

Show each draft in full beside its cited sources, let the PM approve a
subset, and link the created issue keys into Jira after approval.
```

```
feat(frontend): add the activity log with filters and CSV export
```

---

## After the MVP: complete product before FIT4702

**Phase 7. Oversight controls.** Full task state machine (`waiting for information`, `paused`, `stopped`,
`cancelled`) using LangGraph checkpoints; Pause / Stop / Cancel with the semantics in the requirements evaluation;
clarification request cards in the console; mid-task mode change with a review of what to keep; revert where a
change is reversible. Add login and roles (PM approves, developer views), which is required before anyone
outside the team can reach the API, then deploy (Vercel and Render via `deploy.yml`).

*Suggested commit messages* (three PRs):

```
feat(orchestrator): add pause, stop, cancel and mid-task mode change
```

```
feat(auth): add login and roles so only a PM can approve
```

```
chore(deploy): deploy the frontend to Vercel and the API to Render

Turn deploy.yml back on after CI succeeds on main, behind a required
reviewer on the production environment.
```

**Phase 8. M3 Auto-pilot: automations.** M2 runs only when a PM starts it in the console and approves each
proposal. M3 is different: the PM **sets up an automation once**, confirms it, and from then on it runs by
itself in the background for that one task. Every change is logged, and the PM can review it and undo it.

Example: task "estimate story points", instruction "add story points whenever a new task or story is added to
the project", allowed tools `get_issue` and `set_story_points`, allowed field `story points`, at most 20 changes
a day. The PM confirms; the automation then fires on each new issue.

Phase 8 is large. Build it in this order, as separate PRs.

*8a. Automations and grants (backend)*
- Migration: `automations` (name, `task_type`, `instruction`, `trigger_jql`, `poll_seconds`, `allowed_tools`,
  `allowed_fields`, `allowed_action_classes`, `max_changes_per_day`, `project_key`, `status` of `enabled` |
  `paused` | `revoked`, `grant_expires_at`, `shadow_runs_remaining`, `confirmed_by`, `confirmed_at`);
  `runs.automation_id`; `processed_issues` (`automation_id`, `issue_key`, unique together).
- **The approval token becomes an automation grant.** Confirming the setup is the human authorisation: it mints
  a scoped, revocable, expiring grant tied to the automation instead of a per-run token.
  `commit_changes` refuses unless the automation is `enabled`, the grant is unexpired, the tool and field are in
  the allowlist, the action class is not `external`, the project matches, and today's quota is not used up.
- Each background run starts the orchestrator at M3 with **only the automation's allowlisted tools**, so the tool
  layer still enforces the limits (never the prompt).
- Add `JiraClient.set_story_points()` on top of `update_issue_fields`, reading the field id from
  `JIRA_STORY_POINTS_FIELD`. Add a guardrail `update_allowed_fields`: an M3 update may touch only the fields its
  automation lists. This is the one place `create_only` (M2) is widened, per automation and never globally.
- Port the story-point estimation agent from `mcp-test` as the first built-in `task_type`. Phase 3's graph is
  reused; only the tool set and the structured output differ.

*8b. Trigger and scheduler*
- A background loop in the API process polls each enabled automation's `trigger_jql` (for example
  `project = MCP AND created > -5m`) every `poll_seconds`. Webhooks need a public URL, so they are not used.
- `processed_issues` makes each issue run at most once per automation. Triggering is on creation only, and the
  agent's own edits never retrigger it (no loops).
- **Shadow period:** while `shadow_runs_remaining > 0` the automation only proposes, and the PM sees what it
  would have done before it is allowed to write.
- Pausing or revoking takes effect before the next run starts; a run in progress finishes its current write and
  stops.

*8c. Review and undo (API and audit)*
- Every automatic change writes an `audit_log` row with the **before and after value**, the automation id, and
  the model and token counts, so it can be reversed.
- `POST /changes/{id}/undo` is a human action through the API (never an agent tool) that restores the before
  value through `apply.py`. If the field has changed since (current value is not the recorded after value) it
  returns a conflict instead of overwriting. Undo is itself audited.
- **Undoing a created issue** follows fixed rules, because Jira cannot un-create an issue:
  1. The audit log records the key and time of every issue CogniPM creates. Only those keys can be undone; any
     other key is refused before a request is sent.
  2. **Close is the default.** The code reads the issue's available transitions and picks one that leads to a
     done status (workflows differ per site). It adds the `cognipm-reverted` label and a comment. If no such
     transition exists, undo refuses and says why.
  3. **Delete only if untouched.** Read the issue with its changelog and comments; delete only if nobody has
     edited, commented on or linked it, and its sub-tasks are untouched. Otherwise return a conflict and offer
     Close.
  4. Check `GET /mypermissions` first; if the API user cannot delete issues, Close is the only option.
  5. Deletion uses a new method (for example `delete_created_issue`) that trusts the audit log, not the
     `cognipm-sandbox` label. `delete_issue` stays sandbox-only, and neither is ever a gateway tool.
- `scripts/verify_undo.py --confirm` proves it on the real site and prints before and after state: create then
  undo untouched (deleted); create, comment, undo (delete refused, closed instead); undo of a key CogniPM did
  not create (refused, nothing sent). Mock-transport unit tests cover the same cases.
- Endpoints: `GET/POST/PATCH/DELETE /automations`, `POST /automations/{id}/pause` and `/resume`,
  `GET /automations/{id}/runs`.

*8d. Frontend*
- Auto-Pilot page with two tabs: **Configure** (task type, instruction, trigger, allowed tools and fields,
  daily limit, a summary screen the PM must confirm) and **Active automations** (toggle, delete, details, last
  runs). The Activity log gets an "automatic" filter and an **Undo** button on each change.

*Tests (refusal first):* a disabled, paused, revoked or expired automation is refused; a field outside the
allowlist is refused; an `external` action is refused; the daily quota stops further writes; the same issue is
never processed twice; the automation's own edit does not retrigger it; undo is refused with a conflict when the
value changed since; shadow-period runs never write to Jira.

**Done when:** creating a story in the sandbox project sets its story points on its own within one poll
interval, the Activity log shows the change with before and after values, **Undo** restores the old value, and
pausing the automation stops the next issue from being touched.

*Suggested commit messages* (four PRs):

```
feat(automations): add automations with scoped grants and a polling trigger

A PM sets up an automation once. It runs in the background with only its
allowlisted tools, and commit_changes checks the automation's grant,
allowed fields, action class and daily quota. Each issue is processed at
most once, and new automations start in a propose-only shadow period.
```

```
feat(guardrails): allow per-automation field updates with update_allowed_fields

Widen create_only for M3 only, one automation at a time, and keep
external actions refused everywhere.
```

```
feat(audit): record before and after values and add undo

Every automatic change stores the value it replaced. A PM can undo it from
the API; undo is refused with a conflict if the value has changed since.
```

```
feat(frontend): add the Auto-Pilot page and undo in the activity log
```

**Phase 9. Multi-agent and RAG.** The orchestrator routes a request to specialised agents (backlog drafting,
task breakdown, and the story-point estimator that Phase 8 first builds as an automation), each running at its own mode
capped by the task's mode; agent trace in the console. pgvector retrieval over past runs and PM feedback so
proposals cite sources and learn from rejections (stored feedback, not retraining).

**RAG scope and the rule that keeps the study clean.** Large inputs do not need RAG: Gemini's context window
holds a requirements document whole, and chunking it would lower draft quality. RAG is for two things only:
retrieving similar past stories, conventions and definition-of-done rules so drafts match the team's style, and
retrieving PM edits and rejection notes so the agent repeats fewer mistakes. Build it as a read-only
`search_knowledge` gateway tool (present at every mode, so it sits inside the same enforcement), and let a draft
cite retrieved passages labelled "from history" rather than "from input". **Keep RAG identical across every
condition the study compares, or off during evaluation.** If it improves drafts, edit rate improves, and the
study could not tell whether oversight or retrieval caused it. Before building a vector store, try the cheaper
step: put the project's definition of done and a few approved example stories in the prompt (P1 already shows the
model the existing backlog through `context_jql`).

*Suggested commit messages* (two PRs):

```
feat(orchestrator): route requests to specialised agents

Each agent runs at its own mode, capped by the task's mode, and its steps
appear in the console's agent trace.
```

```
feat(rag): retrieve past runs and PM feedback with pgvector

Embed approved drafts and rejection notes so later proposals cite them.
Feedback is stored and retrieved, not used to retrain the model.
```

**Phase 10. Evaluation readiness.** Seeded demo Jira project; study metrics logged (time to decision, edit rate,
rejection rate, overrides); participant onboarding; check alignment with the ethics application; feature freeze
before FIT4702 starts.

*Suggested commit message:*

```
chore: prepare the study release with a demo project and metrics export

Seed a demo Jira project and log the study metrics (time to decision,
edit rate, rejection rate, overrides). Add participant onboarding and
freeze features before FIT4702 starts.
```

---

UI work has its own plan: [ux-plan.md](ux-plan.md) says what pages to add and why, and [ux-phases.md](ux-phases.md)
breaks it into phases U0 to U10 on the branch `feature/uiux-improvement`.

## Hardening and gaps

What a real practitioner would hit that the phases above do not yet cover, from a review on 16 Nov. Each item
says why it matters and where it is scheduled. **Before any real user touches the system, H1 to H6 must be done.**

| # | Gap | Why it matters | Scheduled in |
|---|---|---|---|
| H1 | **Duplicate creates (done in Phase 5)** | A crash or retry between "Jira created the issue" and "the database recorded it" leaves an orphan, and the retry makes a second issue. Stamp each issue with its draft id (a label or issue property) and look for it before creating. | Phase 5 (`apply.py`) |
| H2 | **AI provenance in Jira (done in Phase 5)** | Jira's history shows only the API user, so teammates cannot tell which issues the AI drafted. Add the label `cognipm-drafted` and a comment with run, mode and approver. | Phase 5 |
| H3 | **Login and attribution** | The API has no login: anyone who can reach it can approve a write, and every Jira write comes from one shared token. Add login and roles; decide between a shared bot user and per-user OAuth (3LO) so the approving PM is on record. | Phase 7 |
| H4 | **Privacy and consent** | Project text goes to Gemini and sits in our audit log. Needs participant consent, redaction of personal data before the model call, a retention policy for run text and logs, and agreement with the ethics application (the paper's Privacy Act row). Only synthetic or anonymised data until then. | Phase 10, but design in Phase 5 |
| H5 | **Jira variety** | Create fails on required custom fields; issue-type schemes, team-managed vs company-managed projects, and epic/parent rules differ; 429 rate limits need retry with backoff; search needs pagination. Surface "Jira rejected this because..." in the UI instead of a generic failure. | Phase 4 (required-field check), Phase 5 (retry) |
| H6 | **Review fatigue** | A batch of 30 drafts invites rubber-stamping, which is the central risk of human oversight and the thing the paper studies. Highlight each draft's cited quote in the input, flag assumptions, require explicit ticks (no "approve all" default), and record time per decision. Treat the review screen as a research instrument. | Phase 6 |
| H7 | **Durable runs and model failures (retries and restart recovery done in Phase 5; queue still open)** | A run is an in-process async job, so a restart loses it mid-flight. Gemini 429, timeouts and exhausted credit (seen on 13 Nov, HTTP 402) need bounded retries and a readable message in the UI. Move runs to a persisted queue. | Phase 5 |
| H8 | **Prompt injection from input** | Meeting notes may say "ignore the above". The tool layer still blocks any write the mode does not allow, but drafts could be skewed. Keep `max_items_per_run`, always show provenance, and never act on instructions inside the input. | Phase 4 |
| H9 | **Quality regression** | There is no ground truth. Build a golden set of notes with expected stories and run it on every prompt or model change. Pin the model version (aliases drift) and store a prompt version on each run. | Phase 9, needed for Phase 10 |
| H10 | **Least privilege** | Use a dedicated Jira bot user with only Browse and Create permissions. The current user already cannot delete issues, which is the right direction. Keep secrets only in `.env`. | Setup, before Phase 10 |
| H11 | **Observability and backup** | Structured logs, cost per run, a health endpoint, and DB backups. A database administrator can drop the audit trigger, so back up the audit log and consider hash-chaining rows. | Phase 7 |
| H12 | **Input formats** | Practitioners have PDFs, Word files and meeting transcripts, not pasted text. Add upload with size limits and text extraction. | Phase 6 or 7 |
| H13 | **Notifications** | A PM should be told when a run awaits review (email or Slack). | After the MVP |
| H14 | **Out of scope for now** | SSO, multiple projects, Jira Data Center or Server, localisation, mobile layout. Write them down so the limits are explicit in the report. | Report |

---

## Order at a glance

| Phase | What | Depends on | Part of MVP |
|---|---|---|---|
| 0 | Decisions D1 to D5 | none | yes |
| 1 | Jira integration | 0 | yes |
| 2 | Database and MCP gateway | 1 | yes |
| 3 | Orchestrator (LangGraph, MCP client) | 2 | yes |
| 4 | Guardrails | 2 (chain hook), 3 | yes |
| 5 | Control-plane API | 3, 4 | yes |
| 6 | Frontend: console, approvals, activity log | 5 (6a can start once the contract is drafted) | yes |
| 7 | Task controls, auth, deploy | 6 | no |
| 8 | M3 Auto-pilot: automations, grants, undo | 4, 7 | no |
| 9 | Multi-agent and RAG | 3, 7 | no |
| 10 | Evaluation readiness | all | no |

## What carries over from `mcp-test`

| `mcp-test` | Goes to | Change |
|---|---|---|
| `gateway/jira.py` | `cognipm/gateway/jira.py` | Done; add key validation and comments (Phase 1) |
| `gateway/server.py` | `cognipm/gateway/server.py` | `TOOLS_BY_LEVEL` becomes `TOOLS_BY_MODE` (M1 to M3); Postgres; `propose_estimate_change` becomes `propose_backlog_item` / `propose_task_breakdown` (D3) |
| `gateway/apply.py`, `guardrails.py` | same names | Applies *creates* (parents first), not a value update; guardrail chain instead of one hardcoded check |
| `db/migrations/0001`–`0004`, `db/audit.py` | `cognipm/db/` | One Postgres migration; append-only trigger |
| `orchestrator/mcp_bridge.py`, `agent.py`, `chat.py` | `cognipm/orchestrator/` | Rebuilt on LangGraph; steps persisted |
| `app/jobs.py` | `cognipm/api/` + `run_steps` | SSE from the database instead of an in-memory dict |
| `app/main.py` routes | `cognipm/api/` | JSON API; HTML moves to React |
| `app/templates/*` | `frontend/src/pages/` | Redesigned from the Design canvas |
| `tests/*` | `backend/tests/` | Port the refusal and tool-gating tests first |
| `app/analytics.py`, `charts.py`, dashboard | not in MVP | Revisit after Phase 9 if the study needs it |
