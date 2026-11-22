"""The stories a P2 run can break down: the project's open Stories, for the Agent console's picker."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException

from cognipm.api.deps import get_jira
from cognipm.api.schemas import ProjectOut, StoryOut
from cognipm.gateway.jira import JiraClient, describe_error

router = APIRouter(tags=["stories"])

MAX_STORIES = 50


@router.get("/project", response_model=ProjectOut)
def project(jira: JiraClient = Depends(get_jira)) -> ProjectOut:
    """Which Jira project this CogniPM works in, for the sidebar and the 'Open in Jira' link."""
    base = jira.config.base_url
    return ProjectOut(
        key=jira.config.project_key,
        jira_url=f"{base}/browse/{jira.config.project_key}",
        jira_host=base.removeprefix("https://").removeprefix("http://"),
    )


@router.get("/stories", response_model=list[StoryOut])
def list_stories(jira: JiraClient = Depends(get_jira)) -> list[StoryOut]:
    """Open Stories in the configured project, newest first. Reads Jira; changes nothing."""
    jql = f"project = {jira.config.project_key} AND issuetype = Story AND statusCategory != Done ORDER BY created DESC"
    try:
        issues = jira.search_issues(jql, max_results=MAX_STORIES)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=describe_error(exc)) from exc
    return [
        StoryOut(key=i.key, summary=i.summary, status=i.status, url=f"{jira.config.base_url}/browse/{i.key}")
        for i in issues
    ]
