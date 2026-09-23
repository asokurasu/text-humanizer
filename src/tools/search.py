"""Web search tool.

This is a thin wrapper that declares the tool to the agent. The Anthropic
API provides a server-side web_search tool that we simply surface here
using the matching schema. The agent code passes this tool definition
through to the API in its tools list and does not execute it locally.
"""

from __future__ import annotations

from typing import Any

from claude_engineer.tools.base import Tool, ToolError, ToolResult


class WebSearch(Tool):
    """Surfaces Anthropic's hosted web_search tool to the agent.

    When the API decides to call web_search, the result is fulfilled by
    the Anthropic server rather than locally. We keep a stub `run()`
    method so the tool registry has a uniform interface, but it should
    never actually be invoked on the client side.
    """

    name = "web_search"
    description = (
        "Search the web for current information. Use for questions about "
        "recent events, library documentation, or anything outside the "
        "model's training data."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query.",
            },
        },
        "required": ["query"],
    }

    # The Anthropic API-level tool type, used by Agent when building the
    # tools list sent to the API.
    server_tool_type: str = "web_search_20250305"

    def run(self, query: str) -> ToolResult:  # pragma: no cover
        raise ToolError(
            "web_search is a server-side tool and should be executed by the "
            "Anthropic API, not the local agent."
        )
