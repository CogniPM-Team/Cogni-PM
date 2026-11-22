"""Helpers for the review screen."""

from __future__ import annotations

import re

_QUOTE_VARIANTS = {"'": "['‘’]", '"': '["“”]', "-": "[-–—]"}


def _token_pattern(token: str) -> str:
    return "".join(_QUOTE_VARIANTS.get(ch, re.escape(ch)) for ch in token)


def source_span(text: str | None, quote: str) -> tuple[int, int] | None:
    """Where `quote` sits in `text`, so the review screen can highlight it in the original input.

    Matches the way the orchestrator's check does: ignoring case, runs of whitespace, and curly versus
    straight quotes and dashes. Returns None when it cannot be found (the input was not kept)."""
    tokens = quote.split()
    if not text or not tokens:
        return None
    match = re.search(r"\s+".join(_token_pattern(t) for t in tokens), text, re.IGNORECASE)
    return (match.start(), match.end()) if match else None


def status_note(status: str, *, pending: int) -> str:
    """A plain sentence about what a run's status means and what happens next. What has reached Jira and what
    has not is the part a first-time reviewer gets lost in, so say it every time."""
    if status == "running":
        return "The agent is still working. Nothing has been created in Jira."
    if status == "awaiting_review":
        return "Nothing has been created in Jira yet. Review the drafts, then approve the ones you want."
    if status == "failed":
        if pending:
            return "This run stopped before every draft was created. Approve again to create the rest."
        return "This run failed. Nothing more will be created from it."
    if status == "applied":
        return "Approved. The issues were created in Jira; this run is closed."
    if status == "rejected":
        return "Rejected. Nothing from this run was created in Jira."
    return ""
