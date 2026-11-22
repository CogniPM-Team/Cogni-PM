"""MCP <-> Gemini plumbing shared by every orchestrator entry point: gateway launch
parameters, tool-schema conversion, result unwrapping, and the agent identity string.

Nothing here prints to stdout (log to stderr): the gateway subprocess speaks MCP over stdio.
"""

from __future__ import annotations

import os
import sys

from google.genai import types as genai_types
from mcp import types as mcp_types
from mcp.client.stdio import StdioServerParameters

from cognipm.config import BACKEND_DIR, orchestrator_model


def agent_identity(*, suffix: str | None = None) -> str:
    """The `agent` identity passed to the gateway - lands in runs.agent and audit_log.actor.
    `suffix` tells apart callers that share a model id but are not the same kind of process."""
    base = f"orchestrator:{orchestrator_model()}"
    return f"{base}:{suffix}" if suffix else base


def gateway_params(mode: str, *, suffix: str | None = None) -> StdioServerParameters:
    """How to launch the gateway as a subprocess at `mode`. The orchestrator talks to it only
    through the MCP protocol, never by importing the gateway's tool classes: that is what
    guarantees a run can only do what the gateway registered for its mode."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "cognipm.gateway.server"],
        cwd=str(BACKEND_DIR),
        env={**os.environ, "COGNIPM_MODE": mode, "COGNIPM_AGENT": agent_identity(suffix=suffix)},
    )


def mcp_tools_to_gemini(tools: list[mcp_types.Tool]) -> genai_types.Tool:
    """MCP and Gemini both describe tool parameters as JSON Schema, so this is a
    pass-through, not a translation."""
    return genai_types.Tool(
        function_declarations=[
            genai_types.FunctionDeclaration(
                name=tool.name,
                description=tool.description or "",
                parameters_json_schema=tool.input_schema,
            )
            for tool in tools
        ]
    )


def tool_result_payload(result: mcp_types.CallToolResult) -> object:
    """Prefer structured_content (it matches the tool's Python return type). Fall back to the
    first text block: a tool that returns a plain dict comes back as JSON text."""
    if result.structured_content is not None:
        return result.structured_content
    for block in result.content:
        text = getattr(block, "text", None)
        if text is not None:
            return text
    return None


def function_response_payload(is_error: bool, payload: object) -> dict:
    """What to hand back to Gemini as a function_response.response. A dict goes back as-is
    (MCP already wraps non-object results as {"result": ...}; wrapping again would double-nest)."""
    if is_error:
        return {"error": payload}
    if isinstance(payload, dict):
        return payload
    return {"result": payload}
