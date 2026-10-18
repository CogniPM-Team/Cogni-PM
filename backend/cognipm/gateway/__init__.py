"""The MCP gateway: the only code allowed to touch Jira on an agent's behalf.

Implemented: `jira.py`, the Jira Cloud REST client.

To build (see docs/architecture.md):
  server.py      MCP server. Registers a different tool set per autonomy level via a single
                 TOOLS_BY_LEVEL table - a level that must not write simply never receives the
                 write tools. This is the whole enforcement mechanism.
  guardrails.py  Server-side validators every write path passes through (first one: no change to
                 the due date of a milestone issue). Never a prompt instruction.
  apply.py       The one place a staged change becomes a real Jira write.
"""
