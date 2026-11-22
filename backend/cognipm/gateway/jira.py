"""Jira Cloud REST client (API v3, Basic auth with email + API token).

Credentials come from the environment (loaded from the repo-root .env by
cognipm.config). Nothing in this module prints to stdout - stdio is the MCP
transport, and a stray print() breaks it. Errors go to stderr via `logging`.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

import cognipm.config  # noqa: F401  - loads the repo-root .env

logger = logging.getLogger("cognipm.gateway.jira")

API_VERSION = "3"

# Only issues carrying this label may ever be deleted through this client. Deletion
# exists solely so scripts/verify_write.py can clean up after itself; the gateway
# never exposes it, and the label makes it impossible to point at real work.
SANDBOX_LABEL = "cognipm-sandbox"

# Jira's own limit on an issue summary.
MAX_SUMMARY_LENGTH = 255

_ISSUE_KEY = re.compile(r"[A-Z][A-Z0-9_]+-\d+")
_PROJECT_KEY = re.compile(r"[A-Z][A-Z0-9_]+")


class JiraConfigError(RuntimeError):
    """Raised when required Jira configuration is missing from the environment."""


class InvalidIssueKey(ValueError):
    """A string that is not a Jira issue (or project) key was about to reach a URL or JQL."""


class SandboxOnlyError(PermissionError):
    """Refused: this operation is only allowed on issues labelled SANDBOX_LABEL."""


class NoDoneTransition(RuntimeError):
    """The issue's workflow offers no transition to a done status from where it is."""


def validate_issue_key(key: str) -> str:
    """Return `key` unchanged if it is a well-formed issue key such as MCP-12, else raise.

    Keys reach JQL strings and URL paths, and many come from model output (a draft
    names its parent, a staged change names its issue), so every one is validated
    before any request is built. `fullmatch` matters: `$` would accept a trailing newline.
    """
    if not isinstance(key, str) or not _ISSUE_KEY.fullmatch(key):
        raise InvalidIssueKey(f"not a valid Jira issue key: {key!r}")
    return key


def validate_project_key(key: str) -> str:
    if not isinstance(key, str) or not _PROJECT_KEY.fullmatch(key):
        raise InvalidIssueKey(f"not a valid Jira project key: {key!r}")
    return key


def key_in_jql(keys: list[str]) -> str:
    """`key in (A-1, A-2)` built only from validated keys - the one safe way to put keys into JQL."""
    if not keys:
        raise ValueError("at least one issue key is required")
    return f"key in ({', '.join(validate_issue_key(k) for k in keys)})"


@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    email: str
    api_token: str
    project_key: str
    story_points_field: str

    @classmethod
    def from_env(cls) -> JiraConfig:
        base_url = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
        email = os.environ.get("JIRA_EMAIL", "")
        api_token = os.environ.get("JIRA_API_TOKEN", "")
        project_key = os.environ.get("JIRA_PROJECT_KEY", "")
        story_points_field = os.environ.get("JIRA_STORY_POINTS_FIELD", "")
        missing = [
            name
            for name, val in [
                ("JIRA_BASE_URL", base_url),
                ("JIRA_EMAIL", email),
                ("JIRA_API_TOKEN", api_token),
                ("JIRA_PROJECT_KEY", project_key),
            ]
            if not val
        ]
        if missing:
            raise JiraConfigError(f"Missing required environment variables: {', '.join(missing)}")
        return cls(base_url, email, api_token, project_key, story_points_field)


@dataclass
class Issue:
    key: str
    summary: str
    status: str
    issue_type: str
    story_points: float | None
    due_date: str | None
    labels: list[str]
    description: str | None = None


@dataclass(frozen=True)
class IssueType:
    id: str  # per Jira site: never hardcode
    name: str
    subtask: bool


@dataclass(frozen=True)
class CreatedIssue:
    key: str
    id: str
    url: str  # browse link, for the audit log and the UI


def _normalize_list(payload: Any) -> list[dict]:
    """Jira's endpoints disagree on shape: /field returns a bare JSON array,
    while /search/jql returns {"issues": [...]} and others {"values": [...]}.
    Normalise to a plain list so no call site special-cases it."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and "issues" in payload:
        return payload["issues"]
    if isinstance(payload, dict) and "values" in payload:
        return payload["values"]
    raise ValueError(f"Unrecognised Jira list payload shape: {type(payload)}")


def _adf_to_text(node: Any) -> str:
    """Flatten an Atlassian Document Format node tree to plain text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return node.get("text", "")
    parts = [_adf_to_text(child) for child in node.get("content", []) or []]
    joined = "".join(parts)
    return joined + "\n" if node.get("type") in ("paragraph", "heading") else joined


def text_to_adf(text: str) -> dict:
    """Minimal plain-text -> ADF converter: one paragraph per line."""
    lines = text.split("\n") or [""]
    content = [
        {"type": "paragraph", "content": [{"type": "text", "text": line}] if line else []} for line in lines
    ]
    return {"type": "doc", "version": 1, "content": content}


def draft_to_adf(description: str, acceptance_criteria: list[str] | None = None) -> dict:
    """ADF for a drafted story: the description, then an "Acceptance criteria" heading
    and a bullet list.

    Acceptance criteria live in the description, not a custom field: custom fields
    differ per Jira site, while the description works everywhere.
    """
    content: list[dict] = text_to_adf(description)["content"] if description.strip() else []
    criteria = [c.strip() for c in (acceptance_criteria or []) if c.strip()]
    if criteria:
        content.append(
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Acceptance criteria"}],
            }
        )
        content.append(
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": c}]}],
                    }
                    for c in criteria
                ],
            }
        )
    return {"type": "doc", "version": 1, "content": content}


def describe_error(exc: httpx.HTTPStatusError) -> str:
    """A human-readable reason from a failed Jira call: Jira explains a 400 in
    `errorMessages` and per-field `errors`, which `raise_for_status` hides."""
    status = exc.response.status_code
    try:
        payload = exc.response.json()
    except ValueError:
        return f"Jira returned {status}"
    parts = list(payload.get("errorMessages", [])) + [
        f"{k}: {v}" for k, v in payload.get("errors", {}).items()
    ]
    return f"Jira returned {status}: {'; '.join(parts)}" if parts else f"Jira returned {status}"


class JiraClient:
    """Thin wrapper over the Jira Cloud REST API v3."""

    def __init__(self, config: JiraConfig | None = None, *, transport: httpx.BaseTransport | None = None):
        """`transport` lets tests serve canned responses (httpx.MockTransport) so the
        suite never touches a real Jira site; production leaves it unset."""
        self.config = config or JiraConfig.from_env()
        self._client = httpx.Client(
            base_url=self.config.base_url,
            auth=(self.config.email, self.config.api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30.0,
            transport=transport,
        )
        self._issue_types: list[IssueType] | None = None
        self._required_fields: dict[str, list[dict]] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> JiraClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        resp = self._client.request(method, path, **kwargs)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            logger.error("Jira %s %s -> %s: %s", method, path, resp.status_code, resp.text[:500])
            raise
        return resp

    def myself(self) -> dict:
        return self._request("GET", f"/rest/api/{API_VERSION}/myself").json()

    def get_project(self, project_key: str | None = None) -> dict:
        key = validate_project_key(project_key or self.config.project_key)
        return self._request("GET", f"/rest/api/{API_VERSION}/project/{key}").json()

    def discover_field(self, name_contains: str) -> list[dict]:
        """Fields whose name contains the substring. Used once, by hand, to find a
        custom field id such as story points - the id then belongs in .env."""
        fields = _normalize_list(self._request("GET", f"/rest/api/{API_VERSION}/field").json())
        needle = name_contains.lower()
        return [f for f in fields if needle in f.get("name", "").lower()]

    def _fields(self, *names: str) -> list[str]:
        """The fields to ask Jira for, plus the story-points field when one is configured. That setting is
        optional: an empty one must not become a blank field name in the request."""
        return [*names, *([self.config.story_points_field] if self.config.story_points_field else [])]

    def search_issues(self, jql: str, max_results: int = 50) -> list[Issue]:
        body = {
            "jql": jql,
            "maxResults": max_results,
            "fields": self._fields("summary", "status", "issuetype", "duedate", "labels"),
        }
        payload = self._request("POST", f"/rest/api/{API_VERSION}/search/jql", json=body).json()
        return [self._issue_from_raw(raw) for raw in _normalize_list(payload)]

    def search_issues_for_analytics(self, jql: str, max_results: int = 200) -> list[dict]:
        """Raw per-issue rows for the dashboard: status category, resolution and
        creation dates on top of what search_issues() reads. Kept separate from
        search_issues()/Issue, which is a fixed contract the MCP tool payloads
        depend on. Defaults to a larger page - a dashboard should see the whole
        project, not 50 issues of it."""
        body = {
            "jql": jql,
            "maxResults": max_results,
            "fields": [
                "summary",
                "status",
                "issuetype",
                "duedate",
                "labels",
                "resolutiondate",
                "created",
                *self._fields(),
            ],
        }
        payload = self._request("POST", f"/rest/api/{API_VERSION}/search/jql", json=body).json()
        rows = []
        for raw in _normalize_list(payload):
            fields = raw.get("fields", {})
            status = fields.get("status") or {}
            rows.append(
                {
                    "key": raw["key"],
                    "summary": fields.get("summary", ""),
                    "status": status.get("name", ""),
                    "status_category": (status.get("statusCategory") or {}).get("key", "new"),
                    "issue_type": (fields.get("issuetype") or {}).get("name", ""),
                    "story_points": fields.get(self.config.story_points_field),
                    "due_date": fields.get("duedate"),
                    "resolved_at": fields.get("resolutiondate"),
                    "created": fields.get("created"),
                    "labels": fields.get("labels", []) or [],
                }
            )
        return rows

    def get_issue(self, issue_key: str) -> Issue:
        raw = self._request(
            "GET",
            f"/rest/api/{API_VERSION}/issue/{validate_issue_key(issue_key)}",
            params={
                "fields": ",".join(
                    self._fields("summary", "status", "issuetype", "duedate", "labels", "description")
                )
            },
        ).json()
        return self._issue_from_raw(raw, include_description=True)

    def _issue_from_raw(self, raw: dict, include_description: bool = False) -> Issue:
        fields = raw.get("fields", {})
        return Issue(
            key=raw["key"],
            summary=fields.get("summary", ""),
            status=(fields.get("status") or {}).get("name", ""),
            issue_type=(fields.get("issuetype") or {}).get("name", ""),
            story_points=fields.get(self.config.story_points_field),
            due_date=fields.get("duedate"),
            labels=fields.get("labels", []) or [],
            description=_adf_to_text(fields.get("description")) if include_description else None,
        )

    def update_issue_fields(self, issue_key: str, fields: dict) -> None:
        """PUT field updates to an issue. This client does not enforce
        guardrails - every caller must run cognipm.gateway.guardrails first."""
        self._request(
            "PUT", f"/rest/api/{API_VERSION}/issue/{validate_issue_key(issue_key)}", json={"fields": fields}
        )

    # ---------- creating issues (P1 backlog drafting, P2 task breakdown) ----------
    # Like update_issue_fields, none of these enforce guardrails: the gateway's
    # apply path runs them first. Creating is the only write the MVP needs.

    def list_issue_types(self, project_key: str | None = None) -> list[IssueType]:
        """Issue types the project allows. Ids differ per Jira site, so look types up
        by name here instead of hardcoding an id. Read from the project itself."""
        project = self.get_project(project_key)
        return [
            IssueType(id=str(t["id"]), name=t["name"], subtask=bool(t.get("subtask", False)))
            for t in project.get("issueTypes", [])
        ]

    def issue_type(self, name: str) -> IssueType:
        """The configured project's issue type called `name` (case-insensitive). Cached
        per client: a run looks up the same one or two types many times."""
        if self._issue_types is None:
            self._issue_types = self.list_issue_types()
        for issue_type in self._issue_types:
            if issue_type.name.lower() == name.lower():
                return issue_type
        available = ", ".join(t.name for t in self._issue_types)
        raise ValueError(
            f"No issue type named {name!r} in project {self.config.project_key}. Available: {available}"
        )

    def required_fields(self, issue_type: str) -> list[dict]:
        """Fields Jira insists on when creating `issue_type` in this project and gives no default for,
        as [{"key": ..., "name": ...}]. Differs per project and issue type (custom required fields are
        the usual reason a create is refused), so it is read from Jira, once per type per client."""
        issue_type_id = self.issue_type(issue_type).id
        if issue_type_id not in self._required_fields:
            meta = self._request(
                "GET",
                f"/rest/api/{API_VERSION}/issue/createmeta/{self.config.project_key}/issuetypes/{issue_type_id}",
            ).json()
            self._required_fields[issue_type_id] = [
                {"key": f["key"], "name": f.get("name", f["key"])}
                for f in meta.get("fields", [])
                if f.get("required") and not f.get("hasDefaultValue")
            ]
        return self._required_fields[issue_type_id]

    def create_issue(
        self,
        issue_type: str,
        summary: str,
        *,
        description: dict | None = None,
        parent_key: str | None = None,
        labels: list[str] | None = None,
    ) -> CreatedIssue:
        """Create one issue in the configured project and return its key.

        `issue_type` is a name ("Story", "Task", "Sub-task"). `description` is ADF
        (see draft_to_adf). A sub-task must name its parent. Everything is checked
        before any request is made, so a bad draft never half-reaches Jira.
        """
        summary = summary.strip()
        if not summary:
            raise ValueError("an issue needs a summary")
        if len(summary) > MAX_SUMMARY_LENGTH:
            raise ValueError(f"summary is {len(summary)} characters; Jira allows {MAX_SUMMARY_LENGTH}")
        if parent_key is not None:
            validate_issue_key(parent_key)
        kind = self.issue_type(issue_type)
        if kind.subtask and parent_key is None:
            raise ValueError(f"a {kind.name} needs a parent_key")

        fields: dict[str, Any] = {
            "project": {"key": self.config.project_key},
            "issuetype": {"id": kind.id},
            "summary": summary,
        }
        if description is not None:
            fields["description"] = description
        if parent_key is not None:
            fields["parent"] = {"key": parent_key}
        if labels:
            fields["labels"] = list(labels)

        created = self._request("POST", f"/rest/api/{API_VERSION}/issue", json={"fields": fields}).json()
        return CreatedIssue(
            key=created["key"], id=str(created["id"]), url=f"{self.config.base_url}/browse/{created['key']}"
        )

    def add_comment(self, issue_key: str, text: str) -> None:
        """Add a plain-text comment (sent as ADF). Used to mirror provenance into Jira
        after an approved write; the real record stays in our own database."""
        if not text.strip():
            raise ValueError("a comment needs text")
        self._request(
            "POST",
            f"/rest/api/{API_VERSION}/issue/{validate_issue_key(issue_key)}/comment",
            json={"body": text_to_adf(text)},
        )

    def delete_issue(self, issue_key: str) -> None:
        """Delete an issue and its sub-tasks - but ONLY if it carries SANDBOX_LABEL.

        The label is checked against Jira first, so this cannot be pointed at real
        work even by mistake. Exists for scripts/verify_write.py cleanup only."""
        issue = self._require_sandbox(issue_key, "delete")
        self._request(
            "DELETE", f"/rest/api/{API_VERSION}/issue/{issue.key}", params={"deleteSubtasks": "true"}
        )

    def close_issue(self, issue_key: str) -> str:
        """Move an issue to a done status and return the transition's name - sandbox-labelled issues only.

        Used when delete is refused (the API user may lack "Delete Issues"). Workflows differ
        per site, so the transition is found by its target status category, not by name."""
        issue = self._require_sandbox(issue_key, "close")
        path = f"/rest/api/{API_VERSION}/issue/{issue.key}/transitions"
        transitions = self._request("GET", path).json().get("transitions", [])
        done = next(
            (t for t in transitions if t.get("to", {}).get("statusCategory", {}).get("key") == "done"), None
        )
        if done is None:
            raise NoDoneTransition(f"{issue.key} has no transition to a done status from its current state")
        self._request("POST", path, json={"transition": {"id": done["id"]}})
        return done["name"]

    def _require_sandbox(self, issue_key: str, action: str) -> Issue:
        issue = self.get_issue(issue_key)
        if SANDBOX_LABEL not in issue.labels:
            raise SandboxOnlyError(f"refusing to {action} {issue.key}: it is not labelled {SANDBOX_LABEL!r}")
        return issue
