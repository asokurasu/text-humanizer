"""Built-in tools available to the Claude Engineer agent."""

from claude_engineer.tools.base import Tool, ToolError, ToolResult
from claude_engineer.tools.fs import ReadFile, WriteFile, ListDir
from claude_engineer.tools.shell import RunShell
from claude_engineer.tools.search import WebSearch

BUILTIN_TOOLS: list[Tool] = [
    ReadFile(),
    WriteFile(),
    ListDir(),
    RunShell(),
    WebSearch(),
]

__all__ = [
    "Tool",
    "ToolError",
    "ToolResult",
    "ReadFile",
    "WriteFile",
    "ListDir",
    "RunShell",
    "WebSearch",
    "BUILTIN_TOOLS",
]
