"""M1 (Co-Pilot) conversational Q&A as a small LangGraph tool loop.

    START -> model --(tool calls)--> tools -> model ...
                   \\--(text only)--> END

The model node asks Gemini what to do next. The tools node runs the requested calls through a
real MCP client against the gateway, launched at M1, so the model can only ever call the two
read tools the gateway registered. It cannot stage or apply a change even if asked to: the
tools are not there, and nothing in this file checks the mode.

Multi-turn but stateless per call: the caller keeps the history (chat_messages) and passes it
back in on every turn.
"""

from __future__ import annotations

import os
from typing import Any, TypedDict

from google import genai
from google.genai import types as genai_types
from langgraph.graph import END, START, StateGraph
from mcp.client import Client

from cognipm.config import orchestrator_model
from cognipm.orchestrator.mcp_bridge import (
    function_response_payload,
    gateway_params,
    mcp_tools_to_gemini,
    tool_result_payload,
)
from cognipm.orchestrator.prompts import CHAT_SYSTEM_PROMPT
from cognipm.orchestrator.steps import StepListener

# More read calls than this almost certainly means the question was too broad for one turn:
# fail with a clear message rather than loop.
MAX_TOOL_CALLS = 10


class ChatError(Exception):
    """A chat turn can't produce a final answer: MAX_TOOL_CALLS reached without the model producing text."""


class ChatState(TypedDict):
    contents: list[genai_types.Content]
    pending: list[Any]  # function calls requested by the latest model turn
    calls_made: int
    final_text: str | None
    tool_calls: list[str]


def _build_loop(*, mcp_client: Any, gemini: genai.Client, config: genai_types.GenerateContentConfig, on_step):
    async def call_model(state: ChatState) -> dict:
        contents = list(state["contents"])
        response = await gemini.aio.models.generate_content(
            model=orchestrator_model(), contents=contents, config=config
        )
        content = response.candidates[0].content
        contents.append(content)
        calls = [p.function_call for p in content.parts if p.function_call is not None]
        text = "".join(p.text for p in content.parts if p.text) or None
        return {"contents": contents, "pending": calls, "final_text": None if calls else text}

    async def call_tools(state: ChatState) -> dict:
        contents = list(state["contents"])
        tool_calls = list(state["tool_calls"])
        parts: list[genai_types.Part] = []
        for call in state["pending"]:
            args = dict(call.args or {})
            tool_calls.append(f"{call.name}({args})")
            result = await mcp_client.call_tool(call.name, args)
            payload = tool_result_payload(result)
            if on_step is not None:
                on_step({"phase": "tool", "tool": call.name, "args": args, "ok": not result.is_error})
            parts.append(
                genai_types.Part.from_function_response(
                    name=call.name, response=function_response_payload(result.is_error, payload)
                )
            )
        contents.append(genai_types.Content(role="user", parts=parts))
        return {
            "contents": contents,
            "pending": [],
            "calls_made": state["calls_made"] + len(state["pending"]),
            "tool_calls": tool_calls,
        }

    def after_model(state: ChatState) -> str:
        return "tools" if state["pending"] else END

    def after_tools(state: ChatState) -> str:
        return END if state["calls_made"] >= MAX_TOOL_CALLS else "model"

    graph = StateGraph(ChatState)
    graph.add_node("model", call_model)
    graph.add_node("tools", call_tools)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", after_model, {"tools": "tools", END: END})
    graph.add_conditional_edges("tools", after_tools, {"model": "model", END: END})
    return graph.compile()


async def run_chat_turn(
    *,
    history: list[dict],
    message: str,
    gemini: genai.Client | None = None,
    mcp_server: object | None = None,
    on_step: StepListener | None = None,
) -> tuple[str, list[str]]:
    """Run one M1 chat turn and return (answer_text, tool_calls_made).

    `history` is [{"role": "user" | "agent", "content": str}, ...], oldest first. `gemini` and
    `mcp_server` are injectable for tests: `mcp_server` can be anything `mcp.client.Client`
    accepts, e.g. an in-process server built by build_server("M1", ...), so a test exercises the
    real tool registration without a subprocess or network.
    """
    gemini_client = gemini or genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    async with Client(mcp_server or gateway_params("M1", suffix="chat")) as mcp_client:
        tools = (await mcp_client.list_tools()).tools
        config = genai_types.GenerateContentConfig(
            system_instruction=CHAT_SYSTEM_PROMPT,
            tools=[mcp_tools_to_gemini(tools)],
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        )
        contents = [
            genai_types.Content(
                role="user" if turn["role"] == "user" else "model",
                parts=[genai_types.Part.from_text(text=turn["content"])],
            )
            for turn in history
        ]
        contents.append(genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=message)]))

        graph = _build_loop(mcp_client=mcp_client, gemini=gemini_client, config=config, on_step=on_step)
        state = await graph.ainvoke(
            ChatState(contents=contents, pending=[], calls_made=0, final_text=None, tool_calls=[]),
            config={"recursion_limit": 2 * MAX_TOOL_CALLS + 10},
        )

    # Raised only after the client has exited cleanly: raising inside `async with` would wrap the
    # error in a BaseExceptionGroup (the stdio transport runs an anyio task group).
    if state["final_text"] is None:
        raise ChatError(
            f"The assistant used its read-only tools but gave no final answer within {MAX_TOOL_CALLS} "
            "tool calls - try a narrower question."
        )
    return state["final_text"], state["tool_calls"]
