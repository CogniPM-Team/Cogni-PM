"""What each mode is allowed to do, generated from the gateway's own tool table so the UI cannot drift
from what the gateway actually enforces."""

from __future__ import annotations

import inspect

from fastapi import APIRouter

from cognipm.api.schemas import ModeOut
from cognipm.gateway.server import MODE_NAMES, TOOLS_BY_MODE, GatewayTools

router = APIRouter(tags=["modes"])


def _first_line(tool: str) -> str:
    doc = inspect.getdoc(getattr(GatewayTools, tool)) or ""
    return doc.split("\n\n")[0].replace("\n", " ")


@router.get("/modes", response_model=list[ModeOut])
def list_modes() -> list[ModeOut]:
    return [
        ModeOut(
            id=mode,
            name=MODE_NAMES[mode],
            tools=list(tools),
            can_stage_drafts="start_run" in tools,
            can_commit="commit_changes" in tools,
            tool_help={t: _first_line(t) for t in tools},
        )
        for mode, tools in TOOLS_BY_MODE.items()
    ]
