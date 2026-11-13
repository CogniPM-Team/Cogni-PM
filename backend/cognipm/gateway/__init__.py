"""The MCP gateway: the only code allowed to touch Jira on an agent's behalf.

  jira.py        Jira Cloud REST client, key validation, ADF helpers.
  server.py      MCP server. Registers a different tool set per autonomy mode (M1, M2, M3) via a
                 single TOOLS_BY_MODE table - a mode that must not write simply never receives the
                 write tools. This is the whole enforcement mechanism.
  apply.py       The one place a staged draft becomes a real Jira issue (parents first).
  guardrails.py  Server-side validators every write path passes through. The chain is empty until
                 Phase 4; the milestone rule is ported and waiting for a tool that sets dates.
                 Never a prompt instruction.

Run it by hand: COGNIPM_MODE=M2 python -m cognipm.gateway.server (or use the repo's .mcp.json).
"""
