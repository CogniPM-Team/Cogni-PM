"""Request and response models. FastAPI turns these into the OpenAPI schema, and the frontend's
TypeScript types are generated from that schema, so a field renamed here is a compile error there."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from cognipm.gateway.jira import MAX_SUMMARY_LENGTH

# ---------- requests ----------


class StartRunBody(BaseModel):
    task: Literal["p1", "p2"] = Field(
        description="p1 drafts backlog items from text; p2 breaks one story into sub-tasks"
    )
    input_text: str | None = Field(
        default=None, max_length=200_000, description="p1: the requirements or meeting notes to draft from"
    )
    story_key: str | None = Field(
        default=None, description="p2: the existing story to break down, e.g. MCP-4"
    )
    instructions: str = Field(default="", max_length=4000, description="Extra guidance for the agent")
    document_id: str | None = Field(
        default=None, description="p1: the saved document the text came from, so it can say where it was used"
    )


DocumentKind = Literal["notes", "requirements", "other"]
MAX_DOCUMENT_CHARS = 200_000  # the same limit a run's input has


class DocumentIn(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    kind: DocumentKind = "notes"
    text: str = Field(min_length=1, max_length=MAX_DOCUMENT_CHARS)
    filename: str | None = Field(default=None, max_length=255)


class DocumentRename(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class DocumentSummary(BaseModel):
    id: str
    title: str
    kind: DocumentKind
    filename: str | None
    char_count: int
    created_at: datetime
    updated_at: datetime
    used_in_runs: int = Field(description="Runs that were started from this document")


class DocumentOut(DocumentSummary):
    text: str


class Deleted(BaseModel):
    deleted: int


class ChangeEdit(BaseModel):
    """The fields a PM may change on a draft. Only what is sent is changed."""

    summary: str | None = Field(default=None, min_length=1, max_length=MAX_SUMMARY_LENGTH)
    description: str | None = None
    acceptance_criteria: list[str] | None = None
    labels: list[str] | None = None
    issue_type: Literal["Story", "Task", "Bug"] | None = None


class ApproveBody(BaseModel):
    change_ids: list[str] | None = Field(
        default=None,
        description="The drafts to create. Any pending draft left out is dropped, not created. Omit to approve all.",
    )


class RejectBody(BaseModel):
    comment: str = Field(default="", max_length=4000)


class RerunBody(BaseModel):
    note: str = Field(
        min_length=1, max_length=4000, description="What was wrong; given to the agent as extra instruction"
    )


class ChatBody(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=8000)


# ---------- responses ----------


class RunSummary(BaseModel):
    id: str
    mode: str
    task_type: str
    status: str
    scope: str
    agent: str
    created_at: datetime
    ready_at: datetime | None
    decided_at: datetime | None
    comment: str | None
    rerun_of: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    draft_count: int


class SourceSpan(BaseModel):
    quote: str
    start: int | None = Field(
        description="Where the quote begins in the run's input, or null if it cannot be located"
    )
    end: int | None


class DraftOut(BaseModel):
    id: str
    kind: str
    status: str
    payload: dict = Field(description="Exactly what the agent proposed")
    edited_payload: dict | None = Field(description="The PM's version, when they changed anything")
    effective: dict = Field(description="What will be created: the edited version if there is one")
    parent_change_id: str | None
    sources: list[SourceSpan]
    reasoning: str
    assumptions: str
    action_class: str
    created_issue_key: str | None
    issue_url: str | None
    error: str | None


class StepOut(BaseModel):
    id: int
    ts: datetime
    phase: str
    state: str
    tool: str | None
    detail: dict | None


class ParentStory(BaseModel):
    key: str
    summary: str
    status: str
    url: str


class RunDetail(BaseModel):
    run: RunSummary
    input_text: str | None
    instructions: str | None
    story_key: str | None
    parent_story: ParentStory | None
    drafts: list[DraftOut]
    steps: list[StepOut]
    status_note: str
    editable: bool = Field(description="The PM may still edit drafts")
    can_decide: bool = Field(description="The PM may still approve, reject or rerun")
    seconds_to_decision: float | None = Field(description="Time from ready for review to the PM's decision")


class RunList(BaseModel):
    waiting: list[RunSummary]
    past: list[RunSummary]
    awaiting_review_count: int


class StartedRun(BaseModel):
    run_id: str


class CreatedIssue(BaseModel):
    change_id: str
    issue_key: str
    url: str
    recovered: bool = Field(
        description="Already existed from an earlier, interrupted attempt; not created again"
    )


class ApproveResult(BaseModel):
    run_id: str
    status: str
    created: list[CreatedIssue]
    dropped: list[str] = Field(description="Draft ids the PM left out, which were not created")


class RejectResult(BaseModel):
    run_id: str
    status: str


class RerunResult(BaseModel):
    run_id: str
    rerun_of: str


class ChatResult(BaseModel):
    session_id: str
    title: str = Field(description="The chat's name, taken from the first question until it is renamed")
    answer: str
    tool_calls: list[str]


class ChatFolderOut(BaseModel):
    id: str
    name: str


class ChatSessionOut(BaseModel):
    id: str
    title: str | None
    folder_id: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int


class ChatMessageOut(BaseModel):
    id: int
    role: Literal["user", "agent"]
    content: str
    reads: int | None = Field(
        description="How many times the agent read Jira to answer; null for your own messages"
    )
    created_at: datetime


class ChatSessionDetail(BaseModel):
    session: ChatSessionOut
    messages: list[ChatMessageOut]


class ChatSessionList(BaseModel):
    folders: list[ChatFolderOut]
    sessions: list[ChatSessionOut]


class FolderBody(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class SessionPatch(BaseModel):
    """Only the fields sent are changed. `folder_id: null` takes a chat out of its folder."""

    title: str | None = Field(default=None, max_length=120)
    folder_id: str | None = None


class AuditRow(BaseModel):
    id: int
    ts: datetime
    run_id: str | None
    actor: str
    mode: str | None
    action: str
    outcome: str
    detail: str | None
    before: dict | None
    after: dict | None
    actor_name: str | None = Field(
        default=None, description="The person's name, when the actor is a person who still has an account"
    )


class AuditPage(BaseModel):
    filter: str
    rows: list[AuditRow]


class ModeOut(BaseModel):
    id: str
    name: str
    tools: list[str]
    can_stage_drafts: bool
    can_commit: bool
    tool_help: dict[str, str]


class ProjectOut(BaseModel):
    key: str = Field(description="The Jira project every run works in")
    jira_url: str = Field(description="The project's page in Jira")
    jira_host: str


class LoginBody(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: Literal["pm", "developer"] = Field(description="A PM can change things; a developer can only look")
    disabled: bool


class UserCreate(BaseModel):
    email: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$"),
    ]
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    role: Literal["pm", "developer"]
    password: str = Field(min_length=10, max_length=200)


class UserPatch(BaseModel):
    """Only what is sent is changed."""

    display_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None
    ) = None
    role: Literal["pm", "developer"] | None = None
    disabled: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)


class RefusalCount(BaseModel):
    rule: str
    count: int


class InsightsOut(BaseModel):
    """Counts, not percentages: the page shows "3 of 12", and every rate is one of these over another. Each field is
    defined in docs/phases.md ("Insights: what the numbers mean")."""

    runs_started: int = Field(description="Runs started in the range: the group every other number is about")
    runs_decided: int = Field(description="Of those, approved or rejected")
    runs_open: int = Field(
        description="Still working, waiting for review, or failed part-way: left out of every rate"
    )
    runs_approved: int = Field(description="Decided runs with at least one draft created")
    runs_rejected: int
    drafts_reviewed: int = Field(description="Drafts of decided runs; the next three add up to this")
    drafts_created_as_written: int
    drafts_created_after_edit: int
    drafts_left_out: int
    drafts_edited: int = Field(description="Reviewed drafts whose text differs from the agent's original")
    decisions_timed: int = Field(description="Decided runs that have a time to decision")
    decision_seconds_median: float | None
    decision_seconds_p90: float | None = Field(description="Nearest-rank 90th percentile")
    reruns: int = Field(description="Runs that replace an earlier one")
    refusals: list[RefusalCount]
    refusals_total: int
    tokens_total: int
    tokens_runs: int = Field(description="Runs that have a token figure")
    tokens_average: float | None
    approved_untouched: int = Field(
        description="Approved runs where every draft was created and none was edited"
    )


class ArtifactOut(BaseModel):
    """An issue CogniPM created in Jira."""

    issue_key: str
    url: str
    title: str
    issue_type: str
    run_id: str
    approved_by: str | None
    approved_by_name: str | None = None
    created_at: datetime | None
    jira_state: Literal["found", "missing", "unknown"] = Field(
        description="found: Jira lists it. missing: Jira was asked and it is gone. unknown: Jira could not tell us"
    )
    jira_status: str | None = Field(description="Its status in Jira now (To Do, Done...); only when found")


class ArtifactList(BaseModel):
    items: list[ArtifactOut]
    jira_reachable: bool


class GuardrailOut(BaseModel):
    name: str = Field(description="The rule's id, as it appears in the activity log when it refuses a draft")
    description: str


class SettingsOut(BaseModel):
    """How this CogniPM is set up. Never carries a secret: only whether a key is set, never the key."""

    version: str
    jira_host: str
    jira_project: str
    story_points_field_set: bool
    ai_model: str
    ai_key_set: bool
    max_items_per_run: int
    guardrails: list[GuardrailOut]
    sent_to_model: list[str] = Field(description="Plain sentences: what leaves this machine for the AI model")


class ConnectionTestOut(BaseModel):
    ok: bool
    detail: str | None = Field(
        default=None, description="On success: who or what answered (never an email or key)"
    )
    problem: str | None = Field(default=None, description="On failure: what went wrong and what to check")


class StoryOut(BaseModel):
    key: str
    summary: str
    status: str
    url: str


class ApplyProblem(BaseModel):
    """The body of a 502 when Jira refuses part-way through approving: exactly what happened."""

    message: str
    created: list[CreatedIssue]
    not_created: list[str]
