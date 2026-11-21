"""MCP gateway server.

Registers a different set of tools depending on the autonomy mode. This is the
entire enforcement mechanism: a mode that shouldn't write simply never receives
the write tools - the model is never asked to behave, the tool does not exist
for it to call.

Reads COGNIPM_MODE from the environment at startup (M1, M2 or M3; default M1,
the safest) and COGNIPM_AGENT (default "planning") to say who is driving this
process: a human via Claude Code, or an orchestrator. Nothing here prints to
stdout - stdio is the MCP transport, and a stray print() corrupts the protocol.
"""

from __future__ import annotations

import functools
import os
import threading
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import psycopg
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from psycopg.types.json import Jsonb

from cognipm.config import TOKEN_TTL_MINUTES
from cognipm.db.audit import log_audit
from cognipm.db.connection import get_connection
from cognipm.gateway.apply import ApplyFailed, apply_staged_changes
from cognipm.gateway.guardrails import GuardrailViolation, run_guardrails
from cognipm.gateway.jira import MAX_SUMMARY_LENGTH, Issue, JiraClient, describe_error, validate_issue_key

DEFAULT_AGENT = "planning"
TASK_TYPES = ("p1", "p2")  # P1 backlog drafting, P2 task breakdown
BACKLOG_ISSUE_TYPES = ("Story", "Task", "Bug")  # never an Epic: milestones are off-limits to agents


def _issue_summary(issue: Issue) -> dict:
    return {
        "key": issue.key,
        "summary": issue.summary,
        "status": issue.status,
        "issue_type": issue.issue_type,
        "story_points": issue.story_points,
        "due_date": issue.due_date,
        "labels": issue.labels,
    }


def _clean_list(items: list[str] | None) -> list[str]:
    return [i.strip() for i in (items or []) if isinstance(i, str) and i.strip()]


def _validate_proposal(summary: str, reasoning: str, assumptions: str, sources: list[str]) -> list[str]:
    """Checks every proposal must pass, whatever it proposes. Returns the cleaned sources."""
    if not summary or not summary.strip():
        raise ValueError("summary must not be empty")
    if len(summary.strip()) > MAX_SUMMARY_LENGTH:
        raise ValueError(f"summary must be at most {MAX_SUMMARY_LENGTH} characters")
    if len(reasoning) < 20:
        raise ValueError(
            "reasoning must be at least 20 characters - an unexplained proposal is not a proposal"
        )
    if not assumptions or not assumptions.strip():
        raise ValueError(
            "assumptions must not be empty - state what was assumed, or pass exactly 'NA' if nothing was"
        )
    cleaned = _clean_list(sources)
    if not cleaned:
        raise ValueError(
            "sources must cite at least one passage from the input - a draft that cannot be traced to it is refused"
        )
    return cleaned


class GatewayTools:
    """The tool implementations, holding the shared Jira client and DB connection every tool
    needs. A plain class (not module-level functions) so tests can inject fakes instead of
    hitting the network.

    `agent` says who is driving calls through this instance - "planning" for a human in
    Claude Code, "orchestrator:<model>" for the LangGraph orchestrator - and lands in
    `runs.agent` and `audit_log.actor`.
    """

    def __init__(self, jira: JiraClient, conn: psycopg.Connection, mode: str, agent: str = DEFAULT_AGENT):
        self.jira = jira
        self.conn = conn
        self.mode = mode
        self.agent = agent
        self._lock = threading.Lock()

    @property
    def actor(self) -> str:
        return f"agent:{self.agent}"

    # ---------- registered at every mode (read) ----------

    def search_issues(self, jql: str, max_results: int = 50) -> list[dict]:
        """Search Jira issues by JQL. Returns key, summary, status, story points,
        issue type, due date, and labels for each match."""
        with self._lock:
            issues = self.jira.search_issues(jql, max_results=max_results)
        return [_issue_summary(i) for i in issues]

    def get_issue(self, issue_key: str) -> dict:
        """Full detail for one issue, including its description as plain text."""
        with self._lock:
            issue = self.jira.get_issue(issue_key)
        return _issue_summary(issue) | {"description": issue.description}

    # ---------- registered at M2 and M3 ----------

    def start_run(self, task_type: str, scope: str) -> str:
        """Open a run. Every proposal must belong to one. task_type is 'p1' (draft backlog items
        from requirements or notes) or 'p2' (break one story into sub-tasks). Returns the run_id."""
        if task_type not in TASK_TYPES:
            raise ValueError(f"task_type must be one of {list(TASK_TYPES)}, not {task_type!r}")
        run_id = str(uuid.uuid4())
        with self._lock:
            self.conn.execute(
                "INSERT INTO runs (id, mode, task_type, agent, scope, status) VALUES (%s, %s, %s, %s, %s, 'running')",
                (run_id, self.mode, task_type, self.agent, scope),
            )
            self.conn.commit()
            log_audit(
                self.conn,
                run_id=run_id,
                actor=self.actor,
                mode=self.mode,
                action="start_run",
                outcome="ok",
                detail=f"task_type={task_type} scope={scope}",
            )
        return run_id

    def propose_backlog_item(
        self,
        run_id: str,
        summary: str,
        description: str,
        acceptance_criteria: list[str],
        reasoning: str,
        assumptions: str,
        sources: list[str],
        issue_type: str = "Story",
        labels: list[str] | None = None,
    ) -> str:
        """P1: stage a draft backlog item (a Story, Task or Bug) for a human to review. Writes only
        to the staging table - never touches Jira - so nothing exists in Jira until a human approves.
        `sources` must quote at least one passage of the input the draft comes from. Rejects
        reasoning shorter than 20 characters and empty assumptions (pass 'NA' if none).
        Returns the staged_change_id."""
        cleaned_sources = _validate_proposal(summary, reasoning, assumptions, sources)
        if issue_type not in BACKLOG_ISSUE_TYPES:
            raise ValueError(f"issue_type must be one of {list(BACKLOG_ISSUE_TYPES)}, not {issue_type!r}")
        payload = {
            "issue_type": issue_type,
            "summary": summary.strip(),
            "description": description.strip(),
            "acceptance_criteria": _clean_list(acceptance_criteria),
            "labels": _clean_list(labels),
        }
        with self._lock:
            self._require_open_run(run_id)
            return self._stage(
                run_id,
                "backlog_item",
                payload,
                parent_change_id=None,
                sources=cleaned_sources,
                reasoning=reasoning,
                assumptions=assumptions,
                action="propose_backlog_item",
            )

    def propose_task_breakdown(
        self,
        run_id: str,
        summary: str,
        description: str,
        reasoning: str,
        assumptions: str,
        sources: list[str],
        parent_key: str | None = None,
        parent_change_id: str | None = None,
        labels: list[str] | None = None,
    ) -> str:
        """P2: stage a draft sub-task under a story. Give exactly one parent: `parent_key` (a story
        that already exists in Jira) or `parent_change_id` (another draft in this same run). Writes
        only to the staging table - never touches Jira. Same rules on sources, reasoning and
        assumptions as propose_backlog_item. Returns the staged_change_id."""
        cleaned_sources = _validate_proposal(summary, reasoning, assumptions, sources)
        if (parent_key is None) == (parent_change_id is None):
            raise ValueError("give exactly one parent: parent_key or parent_change_id")
        payload = {
            "summary": summary.strip(),
            "description": description.strip(),
            "labels": _clean_list(labels),
        }
        if parent_key is not None:
            payload["parent_key"] = validate_issue_key(parent_key)
        with self._lock:
            self._require_open_run(run_id)
            if parent_change_id is not None:
                self._require_parent_draft(run_id, parent_change_id)
            return self._stage(
                run_id,
                "subtask",
                payload,
                parent_change_id=parent_change_id,
                sources=cleaned_sources,
                reasoning=reasoning,
                assumptions=assumptions,
                action="propose_task_breakdown",
            )

    def finish_run(self, run_id: str) -> dict:
        """Mark a run awaiting_review and return a summary of its drafts for the human."""
        with self._lock:
            self._require_open_run(run_id)
            rows = self.conn.execute(
                "SELECT id, kind, payload->>'summary' AS summary, parent_change_id FROM staged_changes "
                "WHERE run_id = %s ORDER BY created_at, id",
                (run_id,),
            ).fetchall()
            self.conn.execute(
                "UPDATE runs SET status = 'awaiting_review', ready_at = now() WHERE id = %s", (run_id,)
            )
            self.conn.commit()
            log_audit(
                self.conn,
                run_id=run_id,
                actor=self.actor,
                mode=self.mode,
                action="finish_run",
                outcome="awaiting_review",
                detail=f"{len(rows)} staged drafts",
            )
        return {"run_id": run_id, "status": "awaiting_review", "staged_changes": rows}

    # ---------- registered at M3 only ----------

    def commit_changes(self, run_id: str, approval_token: str) -> dict:
        """Create the run's staged drafts in Jira. Requires an approval_token issued by a human
        through the API. Fails loudly - and creates nothing - if the token is missing, unknown,
        expired, already consumed, or for a different run."""
        with self._lock:
            token_row = self.conn.execute(
                "SELECT run_id, issued_at, expires_at, consumed_at FROM approval_tokens WHERE token = %s",
                (approval_token,),
            ).fetchone()
            self._require_valid_token(token_row, run_id)

            try:
                applied = apply_staged_changes(
                    self.jira, self.conn, run_id, actor=self.actor, mode=self.mode, automatic=True
                )
            except ApplyFailed as failure:
                # The token stays unconsumed so a retry can create what is left.
                self.conn.execute("UPDATE runs SET status = 'failed' WHERE id = %s", (run_id,))
                self.conn.commit()
                log_audit(
                    self.conn,
                    run_id=run_id,
                    actor=self.actor,
                    mode=self.mode,
                    action="commit_changes",
                    outcome="failed",
                    detail=str(failure),
                )
                raise

            self.conn.execute(
                "UPDATE approval_tokens SET consumed_at = %s WHERE token = %s",
                (datetime.now(UTC), approval_token),
            )
            self.conn.execute("UPDATE runs SET status = 'applied' WHERE id = %s", (run_id,))
            self.conn.commit()
            keys = [a["issue_key"] for a in applied]
            log_audit(
                self.conn,
                run_id=run_id,
                actor=self.actor,
                mode=self.mode,
                action="commit_changes",
                outcome="applied",
                detail=f"{len(applied)} issue(s): {keys}",
            )
        return {"run_id": run_id, "created_issue_keys": keys}

    # ---------- helpers ----------

    def _stage(
        self,
        run_id: str,
        kind: str,
        payload: dict,
        *,
        parent_change_id: str | None,
        sources: list[str],
        reasoning: str,
        assumptions: str,
        action: str,
    ) -> str:
        # The same chain runs again, against Jira's state at that moment, just before the write.
        run_guardrails(
            {
                "kind": kind,
                "payload": payload,
                "parent_change_id": parent_change_id,
                "action_class": "structural",
            },
            jira=self.jira,
            conn=self.conn,
            run_id=run_id,
            actor=self.actor,
            mode=self.mode,
            stage="propose",
        )
        change_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO staged_changes (id, run_id, kind, payload, parent_change_id, sources, reasoning, assumptions) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                change_id,
                run_id,
                kind,
                Jsonb(payload),
                parent_change_id,
                Jsonb(sources),
                reasoning,
                assumptions,
            ),
        )
        self.conn.commit()
        log_audit(
            self.conn,
            run_id=run_id,
            actor=self.actor,
            mode=self.mode,
            action=action,
            outcome="staged",
            detail=f"{kind}: {payload['summary']}",
            after=payload,
        )
        return change_id

    def _require_open_run(self, run_id: str) -> None:
        run = self.conn.execute("SELECT status FROM runs WHERE id = %s", (run_id,)).fetchone()
        if run is None:
            raise ValueError(f"unknown run_id {run_id!r}; call start_run first")
        if run["status"] != "running":
            raise ValueError(f"run {run_id} is {run['status']}, not running; start a new run")

    def _require_parent_draft(self, run_id: str, parent_change_id: str) -> None:
        parent = self.conn.execute(
            "SELECT run_id, kind FROM staged_changes WHERE id = %s", (parent_change_id,)
        ).fetchone()
        if parent is None or parent["run_id"] != run_id:
            raise ValueError(f"parent_change_id {parent_change_id!r} is not a draft in run {run_id}")
        if parent["kind"] == "subtask":
            raise ValueError("a sub-task cannot be the parent of another sub-task")

    def _require_valid_token(self, token_row: dict | None, run_id: str) -> None:
        if token_row is None:
            self._refuse_commit(run_id, "approval_token is missing or unknown")
        if token_row["run_id"] != run_id:
            self._refuse_commit(run_id, "approval_token belongs to a different run")
        if token_row["consumed_at"] is not None:
            self._refuse_commit(run_id, "approval_token has already been consumed")
        if token_row["expires_at"] < datetime.now(UTC):
            self._refuse_commit(run_id, "approval_token has expired")
        stale = self.conn.execute(
            "SELECT 1 FROM staged_changes WHERE run_id = %s AND status IN ('proposed', 'failed') AND created_at > %s",
            (run_id, token_row["issued_at"]),
        ).fetchone()
        if stale:
            self._refuse_commit(run_id, "a draft was staged after this approval was issued; approve again")

    def _refuse_commit(self, run_id: str, reason: str) -> None:
        log_audit(
            self.conn,
            run_id=run_id,
            actor=self.actor,
            mode=self.mode,
            action="commit_changes",
            outcome="refused",
            detail=reason,
        )
        raise ValueError(reason)


def issue_approval_token(
    conn: psycopg.Connection, run_id: str, *, ttl_minutes: int = TOKEN_TTL_MINUTES
) -> str:
    """Mint a token for one run. A human action: the API calls this when a PM approves.
    It is deliberately not a gateway tool, so an agent can never obtain one."""
    token = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO approval_tokens (token, run_id, expires_at) VALUES (%s, %s, %s)",
        (token, run_id, datetime.now(UTC) + timedelta(minutes=ttl_minutes)),
    )
    conn.commit()
    return token


READ_TOOL_NAMES = ("search_issues", "get_issue")
PROPOSE_TOOL_NAMES = ("start_run", "propose_backlog_item", "propose_task_breakdown", "finish_run")
COMMIT_TOOL_NAMES = ("commit_changes",)

# The whole enforcement mechanism lives in this one table: adding a mode is
# listing tool names here, never restructuring the tools themselves.
TOOLS_BY_MODE: dict[str, tuple[str, ...]] = {
    "M1": READ_TOOL_NAMES,
    "M2": READ_TOOL_NAMES + PROPOSE_TOOL_NAMES,
    "M3": READ_TOOL_NAMES + PROPOSE_TOOL_NAMES + COMMIT_TOOL_NAMES,
}


MODE_NAMES = {"M1": "Co-Pilot", "M2": "Super-Pilot", "M3": "Auto-Pilot"}


def _refusals_reach_the_caller(tool):
    """The MCP server hides the text of any exception a tool raises (it could be anything, including
    a secret), so the caller would only learn "Error executing tool". A refusal is deliberate and
    safe to explain - an agent cannot fix a draft it is not told is wrong - so turn the exceptions
    we raise on purpose into ToolError, which is passed through. Anything else stays a masked crash."""

    @functools.wraps(tool)
    def call(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        except (ValueError, GuardrailViolation, ApplyFailed) as exc:
            raise ToolError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise ToolError(describe_error(exc)) from exc

    return call


def build_server(
    mode: str,
    jira: JiraClient | None = None,
    conn: psycopg.Connection | None = None,
    agent: str = DEFAULT_AGENT,
) -> MCPServer:
    """Build the MCP server with exactly the tools `mode` is allowed to see."""
    if mode not in TOOLS_BY_MODE:
        raise ValueError(f"Unknown mode {mode!r}; must be one of {sorted(TOOLS_BY_MODE)}")

    tools = GatewayTools(jira=jira or JiraClient(), conn=conn or get_connection(), mode=mode, agent=agent)
    server: MCPServer = MCPServer(name="cognipm")
    registry = {
        "search_issues": tools.search_issues,
        "get_issue": tools.get_issue,
        "start_run": tools.start_run,
        "propose_backlog_item": tools.propose_backlog_item,
        "propose_task_breakdown": tools.propose_task_breakdown,
        "finish_run": tools.finish_run,
        "commit_changes": tools.commit_changes,
    }
    for name in TOOLS_BY_MODE[mode]:
        server.add_tool(_refusals_reach_the_caller(registry[name]), name=name)
    return server


def main() -> None:
    mode = os.environ.get("COGNIPM_MODE", "M1")
    agent = os.environ.get("COGNIPM_AGENT", DEFAULT_AGENT)
    server = build_server(mode, agent=agent)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
