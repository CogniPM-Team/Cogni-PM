"""Agent orchestration: LangGraph graphs that drive Gemini and the gateway.

  tasks.py       run_task: M2 runs. P1 drafts backlog items from pasted text, P2 breaks one story
                 into sub-tasks. Gemini returns schema-checked JSON, every cited quote is checked
                 against the input, then the drafts are staged through the gateway.
  chat.py        run_chat_turn: the M1 read-only Q&A tool loop.
  mcp_bridge.py  launching the gateway as a subprocess; MCP <-> Gemini conversion.
  steps.py       run_steps and token counts persisted to the database.

It must call the gateway as a real MCP client over the same protocol Claude Code uses, never by
importing the gateway's tool classes: that is what guarantees a run can only do what the gateway
registered for its mode.
"""
