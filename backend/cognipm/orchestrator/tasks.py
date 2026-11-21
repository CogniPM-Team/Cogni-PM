"""M2 task runs: P1 (draft backlog items from pasted requirements or notes) and P2 (break one
existing story into sub-tasks), as a LangGraph graph:

    open_run -> analyse -> generate -> verify --(nothing usable, retries left)--> generate
                                          \\--> stage -> END

The model never touches Jira and has no tools in this graph. Gemini is asked for JSON that is
validated against a Pydantic schema (schemas.py), every cited passage is checked to really appear
in the input, and only then does this code call the gateway - as a real MCP client over stdio,
launched at the run's mode - to open the run, stage each draft and finish. So a run can do only what
the gateway registered for its mode: at M1 `start_run` does not exist, and the run cannot begin.

Errors never propagate from inside a node. They are recorded and carried to the end of the graph,
then raised after the MCP client has exited: raising inside `async with Client(...)` would wrap
them in a BaseExceptionGroup (the stdio transport runs an anyio task group).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from langgraph.graph import END, START, StateGraph
from mcp.client import Client
from pydantic import ValidationError

from cognipm.config import orchestrator_model
from cognipm.db.connection import Connection
from cognipm.orchestrator.mcp_bridge import gateway_params, tool_result_payload
from cognipm.orchestrator.prompts import P1_SYSTEM_PROMPT, P2_SYSTEM_PROMPT, build_p1_prompt, build_p2_prompt
from cognipm.orchestrator.schemas import BacklogDrafts, SubtaskDrafts
from cognipm.orchestrator.steps import StepListener, StepRecorder, mark_run_failed, record_input, record_usage

MAX_ATTEMPTS = 2  # generation attempts when nothing usable comes back
MAX_EXISTING_SHOWN = 30  # existing backlog items shown to the model so it avoids duplicates


class OrchestratorError(Exception):
    """The run cannot complete. The message says why; the run is marked failed if it had started."""


@dataclass
class TaskResult:
    run_id: str
    change_ids: list[str]
    dropped: list[str]  # drafts or quotes that were left out, and why


class _GraphState(TypedDict):
    done: bool


@dataclass
class _Run:
    """Everything one run needs, with the graph's nodes as methods."""

    task: Literal["p1", "p2"]
    mode: str
    conn: Connection
    mcp: Any
    gemini: genai.Client
    rec: StepRecorder
    rerun_of: str | None = None
    on_run_started: Callable[[str], None] | None = None
    input_text: str = ""
    story_key: str | None = None
    context_jql: str | None = None
    instructions: str = ""
    scope: str = ""
    run_id: str | None = None
    attempt: int = 0
    feedback: str = ""
    drafts: list[dict] = field(default_factory=list)  # validated, sources checked
    dropped: list[str] = field(default_factory=list)
    change_ids: list[str] = field(default_factory=list)
    existing: str = ""
    error: str | None = None

    # ---------- gateway access ----------

    async def call(self, tool: str, **args: object) -> object:
        """Call a gateway tool over MCP. Raises on a refusal (including 'unknown tool')."""
        result = await self.mcp.call_tool(tool, args)
        payload = tool_result_payload(result)
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                pass
        if isinstance(payload, dict) and set(payload) == {"result"}:
            payload = payload["result"]
        if result.is_error:
            raise RuntimeError(str(payload))
        return payload

    def guarded(self, phase: str, node):
        """Turn an exception in a node into a recorded error that ends the graph."""

        async def run(state: _GraphState) -> dict:
            if self.error:
                return {}
            try:
                await node()
            except Exception as exc:  # noqa: BLE001 - recorded, then raised after the client exits
                self.error = (
                    str(exc) if isinstance(exc, OrchestratorError) else f"{type(exc).__name__}: {exc}"
                )
                self.rec(phase, "error", reason=self.error)
            return {}

        return run

    # ---------- nodes ----------

    async def open_run(self) -> None:
        try:
            self.run_id = await self.call("start_run", task_type=self.task, scope=self.scope)
        except RuntimeError as exc:
            raise OrchestratorError(f"the gateway at {self.mode} refused to open a run: {exc}") from exc
        self.rec.run_id = self.run_id
        record_input(
            self.conn,
            self.run_id,
            input_text=self.input_text or None,
            instructions=self.instructions or None,
            story_key=self.story_key,
            rerun_of=self.rerun_of,
        )
        self.rec("analysing", "start", tool="start_run", mode=self.mode, task=self.task)
        if self.on_run_started is not None:
            self.on_run_started(self.run_id)  # the caller can now hand the run's id to a person

    async def analyse(self) -> None:
        if self.task == "p2":
            issue = await self.call("get_issue", issue_key=self.story_key)
            self.rec("analysing", "end", tool="get_issue", key=self.story_key)
            self.input_text = f"{issue['summary']}\n\n{issue.get('description') or ''}".strip()
            record_input(self.conn, self.run_id, input_text=self.input_text)
            if not (issue.get("description") or "").strip():
                raise OrchestratorError(f"{self.story_key} has no description to break down")
        elif self.context_jql:
            found = await self.call("search_issues", jql=self.context_jql, max_results=MAX_EXISTING_SHOWN)
            self.existing = "\n".join(f"{i['key']}: {i['summary']}" for i in found)
            self.rec("analysing", "end", tool="search_issues", existing=len(found))
        else:
            self.rec("analysing", "end")

    async def generate(self) -> None:
        self.attempt += 1
        self.rec("generating", "start", attempt=self.attempt)
        if self.task == "p1":
            system, schema = P1_SYSTEM_PROMPT, BacklogDrafts
            prompt = build_p1_prompt(
                input_text=self.input_text,
                existing=self.existing,
                instructions=self.instructions,
                feedback=self.feedback,
            )
        else:
            system, schema = P2_SYSTEM_PROMPT, SubtaskDrafts
            prompt = build_p2_prompt(
                story_key=self.story_key or "",
                story_text=self.input_text,
                instructions=self.instructions,
                feedback=self.feedback,
            )
        config = genai_types.GenerateContentConfig(
            system_instruction=system, response_mime_type="application/json", response_schema=schema
        )
        model = orchestrator_model()
        response = await _generate_with_retry(self.gemini, model, prompt, config, self.rec, self.attempt)
        usage = getattr(response, "usage_metadata", None)
        record_usage(
            self.conn,
            self.run_id,
            model=model,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        )

        try:
            parsed = schema.model_validate_json(response.text)
        except ValidationError as exc:
            # A malformed draft never gets as far as the gateway.
            self.drafts = []
            self.feedback = f"The reply did not match the required schema: {exc.errors()[0]['msg']}"
            self.dropped.append(self.feedback)
            self.rec("generating", "end", attempt=self.attempt, drafts=0, schema_error=self.feedback)
            return
        self.drafts = [item.model_dump() for item in parsed.items]
        self.rec("generating", "end", attempt=self.attempt, drafts=len(self.drafts))

    async def verify(self) -> None:
        """Keep only quotes that really appear in the input, and only drafts that keep one."""
        self.rec("verifying", "start")
        haystack = _normalise(self.input_text)
        kept, problems = [], []
        for draft in self.drafts:
            good = [s for s in draft["sources"] if _normalise(s) in haystack]
            bad = [s for s in draft["sources"] if s not in good]
            for source in bad:
                problems.append(f"'{draft['summary']}': this quote is not in the input: {source[:80]!r}")
            if good:
                kept.append({**draft, "sources": good})
            else:
                problems.append(f"'{draft['summary']}': dropped, none of its quotes appear in the input")
        self.drafts = kept
        self.dropped.extend(problems)
        if problems:
            self.feedback = "\n".join(problems) + "\nQuote the input exactly, word for word."
        self.rec("verifying", "end", kept=len(kept), problems=problems)

    async def stage(self) -> None:
        if not self.drafts:
            problems = "; ".join(self.dropped) or "the model returned no drafts"
            raise OrchestratorError(
                f"no draft could be traced to the input, so nothing was staged ({problems})"
            )
        propose = "propose_backlog_item" if self.task == "p1" else "propose_task_breakdown"
        for draft in self.drafts:
            args = {
                k: draft[k]
                for k in ("summary", "description", "reasoning", "assumptions", "sources", "labels")
            }
            args["run_id"] = self.run_id
            if self.task == "p1":
                args |= {
                    "issue_type": draft["issue_type"],
                    "acceptance_criteria": draft["acceptance_criteria"],
                }
            else:
                args["parent_key"] = self.story_key
            self.rec("staging", "start", tool=propose, summary=draft["summary"])
            try:
                self.change_ids.append(await self.call(propose, **args))
                self.rec("staging", "end", tool=propose, summary=draft["summary"])
            except RuntimeError as exc:  # the gateway is the final authority on a draft
                self.dropped.append(f"'{draft['summary']}': the gateway refused it: {exc}")
                self.rec("staging", "error", tool=propose, summary=draft["summary"], reason=str(exc))
        if not self.change_ids:
            raise OrchestratorError("the gateway refused every draft, so nothing was staged")
        await self.call("finish_run", run_id=self.run_id)
        self.rec("staging", "end", tool="finish_run", drafts=len(self.change_ids))

    # ---------- routing ----------

    def after_open(self, state: _GraphState) -> str:
        return END if self.error else "analyse"

    def after_analyse(self, state: _GraphState) -> str:
        return END if self.error else "generate"

    def after_generate(self, state: _GraphState) -> str:
        return END if self.error else "verify"

    def after_verify(self, state: _GraphState) -> str:
        if self.error:
            return END
        if not self.drafts and self.attempt < MAX_ATTEMPTS:
            return "generate"  # nothing usable: try once more, telling the model what was wrong
        return "stage"

    def build(self):
        graph = StateGraph(_GraphState)
        graph.add_node("open_run", self.guarded("analysing", self.open_run))
        graph.add_node("analyse", self.guarded("analysing", self.analyse))
        graph.add_node("generate", self.guarded("generating", self.generate))
        graph.add_node("verify", self.guarded("verifying", self.verify))
        graph.add_node("stage", self.guarded("staging", self.stage))
        graph.add_edge(START, "open_run")
        graph.add_conditional_edges("open_run", self.after_open, {"analyse": "analyse", END: END})
        graph.add_conditional_edges("analyse", self.after_analyse, {"generate": "generate", END: END})
        graph.add_conditional_edges("generate", self.after_generate, {"verify": "verify", END: END})
        graph.add_conditional_edges(
            "verify", self.after_verify, {"generate": "generate", "stage": "stage", END: END}
        )
        graph.add_edge("stage", END)
        return graph.compile()


RETRY_DELAYS = (2.0, 6.0)  # seconds to wait before each retry of a model call: three tries in all
_RETRYABLE = (
    429,
    500,
    502,
    503,
    504,
)  # rate limit and server trouble; 402 (no credit) or 400 are not worth retrying


async def _generate_with_retry(gemini, model, prompt, config, rec: StepRecorder, attempt: int):
    """One model call, retried a bounded number of times when Gemini is rate-limiting or briefly unwell."""
    for delay in (*RETRY_DELAYS, None):
        try:
            return await gemini.aio.models.generate_content(model=model, contents=prompt, config=config)
        except genai_errors.APIError as exc:
            if delay is None or exc.code not in _RETRYABLE:
                raise
            rec("generating", "retry", attempt=attempt, code=exc.code, wait_seconds=delay)
            await asyncio.sleep(delay)


def _normalise(text: str) -> str:
    """Whitespace, case and typographic quotes/dashes must not make a real quote look fake."""
    text = text.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"}))
    return re.sub(r"\s+", " ", text).strip().casefold()


async def run_task(
    *,
    conn: Connection,
    task: Literal["p1", "p2"],
    input_text: str = "",
    story_key: str | None = None,
    context_jql: str | None = None,
    instructions: str = "",
    scope: str | None = None,
    mode: str = "M2",
    gemini: genai.Client | None = None,
    mcp_server: object | None = None,
    on_step: StepListener | None = None,
    rerun_of: str | None = None,
    on_run_started: Callable[[str], None] | None = None,
) -> TaskResult:
    """Run P1 (give `input_text`) or P2 (give `story_key`) and return once the drafts are staged and
    the run is `awaiting_review`. Nothing is created in Jira.

    `conn` is used only for the orchestrator's own bookkeeping (run_steps, token counts, marking a
    run failed); every other read and write goes through the gateway. `context_jql` (P1) shows the
    model existing backlog items so it avoids duplicates. `gemini` and `mcp_server` are injectable
    for tests: `mcp_server` can be anything `mcp.client.Client` accepts, e.g. an in-process server
    from build_server(), so a test exercises the real tool registration without a subprocess.

    Raises OrchestratorError if the run cannot be opened (the mode has no `start_run`), the story
    cannot be read, no draft can be traced to the input, or the gateway refuses every draft.
    """
    if task == "p1" and not input_text.strip():
        raise ValueError("P1 needs input_text: the requirements or meeting notes to draft from")
    if task == "p2" and not story_key:
        raise ValueError("P2 needs story_key: the story to break down")

    gemini_client = gemini or genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    run: _Run | None = None

    async with Client(mcp_server or gateway_params(mode)) as mcp_client:
        run = _Run(
            task=task,
            mode=mode,
            conn=conn,
            mcp=mcp_client,
            gemini=gemini_client,
            rec=StepRecorder(conn, on_step),
            rerun_of=rerun_of,
            on_run_started=on_run_started,
            input_text=input_text,
            story_key=story_key,
            context_jql=context_jql,
            instructions=instructions,
            scope=scope or (f"story {story_key}" if task == "p2" else "pasted text"),
        )
        await run.build().ainvoke({"done": False}, config={"recursion_limit": 25})

    if run.error:
        if run.run_id:
            mark_run_failed(conn, run.run_id, run.error)
        raise OrchestratorError(run.error)
    return TaskResult(run_id=run.run_id, change_ids=run.change_ids, dropped=run.dropped)
