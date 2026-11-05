"""The local SDK server: the HTTP API the web app uses to validate, compile and test agents (PLAN 16.12)."""

from agentbuilder.server.app import LocalServer, build_server

__all__ = ["LocalServer", "build_server"]
