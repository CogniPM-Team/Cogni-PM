"""A scripted stand-in for the Gemini client. A real model call is non-deterministic and costs
money; it does not belong in the suite that runs on every push. The tests drive the real
gateway tool registration and the real graphs, with only the LLM itself faked."""

from __future__ import annotations

import json
from types import SimpleNamespace

from google.genai import types as genai_types


class _Models:
    def __init__(self, replies: list):
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def generate_content(self, *, model, contents, config):
        # Snapshot: the caller keeps appending to the list it passed.
        self.calls.append(
            {
                "model": model,
                "contents": list(contents) if isinstance(contents, list) else contents,
                "config": config,
            }
        )
        reply = self.replies.pop(0) if self.replies else self.replies_exhausted()
        return reply(contents) if callable(reply) else reply

    @staticmethod
    def replies_exhausted():
        raise AssertionError("the code asked Gemini for more replies than the test scripted")


class FakeGemini:
    """`FakeGemini([reply, ...])`: each call to generate_content returns the next reply."""

    def __init__(self, replies: list):
        self.models = _Models(replies)
        self.aio = SimpleNamespace(models=self.models)

    @property
    def calls(self) -> list[dict]:
        return self.models.calls

    @property
    def prompts(self) -> list[str]:
        return [c["contents"] for c in self.calls if isinstance(c["contents"], str)]


def drafts_reply(items: list[dict], *, prompt_tokens: int = 100, output_tokens: int = 50):
    """A structured-output reply: JSON matching BacklogDrafts or SubtaskDrafts."""
    return SimpleNamespace(
        text=json.dumps({"items": items}),
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens, candidates_token_count=output_tokens
        ),
    )


def raw_text_reply(text: str):
    return SimpleNamespace(text=text, usage_metadata=None)


def _content_reply(part):
    content = genai_types.Content(role="model", parts=[part])
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)])


def call_reply(name: str, **args):
    """A chat reply asking to call a tool."""
    return _content_reply(genai_types.Part.from_function_call(name=name, args=args))


def text_chat_reply(text: str):
    return _content_reply(genai_types.Part.from_text(text=text))


def backlog_item(summary: str, *quotes: str, **overrides) -> dict:
    return {
        "summary": summary,
        "description": f"Details for {summary}.",
        "reasoning": "The input asks for this directly.",
        "assumptions": "NA",
        "sources": list(quotes),
        "issue_type": "Story",
        "acceptance_criteria": ["It works as described"],
        "labels": [],
    } | overrides


def subtask(summary: str, *quotes: str, **overrides) -> dict:
    return {
        "summary": summary,
        "description": f"Do: {summary}.",
        "reasoning": "The story needs this piece of work.",
        "assumptions": "NA",
        "sources": list(quotes),
        "labels": [],
    } | overrides
