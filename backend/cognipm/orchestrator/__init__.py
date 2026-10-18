"""Agent orchestration (empty - to be built).

Drives agent runs with LangGraph. It must call the gateway as a real MCP client over the
same protocol Claude Code uses, never by importing the gateway's tool classes: that is what
guarantees an agent can only do what the gateway registered for its level.
"""
