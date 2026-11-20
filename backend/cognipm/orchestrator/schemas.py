"""The shape of a draft as Gemini must return it. Gemini is asked for JSON matching these
models and the reply is validated against them, so a malformed draft is rejected here -
before anything reaches the gateway, let alone Jira."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from cognipm.gateway.jira import MAX_SUMMARY_LENGTH


class _Draft(BaseModel):
    summary: str = Field(min_length=1, max_length=MAX_SUMMARY_LENGTH, description="One-line title.")
    description: str = Field(description="What is wanted and why, in plain prose.")
    reasoning: str = Field(
        min_length=20,
        description="Why this item exists and why it is shaped this way. At least 20 characters.",
    )
    assumptions: str = Field(
        min_length=1, description="What you assumed that a PM should check, or exactly 'NA' if nothing."
    )
    sources: list[str] = Field(
        min_length=1,
        description="Passages copied VERBATIM from the input that this item comes from. Never paraphrase.",
    )


class BacklogDraft(_Draft):
    issue_type: Literal["Story", "Task", "Bug"] = "Story"
    acceptance_criteria: list[str] = Field(
        min_length=1, description="Testable statements that say when the item is done."
    )
    labels: list[str] = Field(default_factory=list)


class SubtaskDraft(_Draft):
    labels: list[str] = Field(default_factory=list)


class BacklogDrafts(BaseModel):
    items: list[BacklogDraft]


class SubtaskDrafts(BaseModel):
    items: list[SubtaskDraft]
