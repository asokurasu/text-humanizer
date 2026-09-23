"""Shell command execution tool."""

from __future__ import annotations

import subprocess
from typing import Any

from claude_engineer.tools.base import Tool, ToolError, ToolResult


DEFAULT_TIMEOUT = 60  # seconds
MAX_OUTPUT_CHARS = 20_000


class RunShell(Tool):
    name = "run_shell"
    description = (
        "Execute a shell command in the current working directory and return "
        "its combined stdout/stderr plus exit code. Commands run with a 60s "
        "timeout by default."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to run, as a single string.",
            },
            "timeout": {
                "type": "integer",
                "description": "Optional timeout in seconds (default 60).",
            },
        },
        "required": ["command"],
    }

    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> ToolResult:
        if not command.strip():
            raise ToolError("Empty command.")

        try:
            completed = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise ToolError(f"Command timed out after {timeout}s: {command!r}")
        except OSError as exc:
            raise ToolError(f"Could not run command: {exc}") from exc

        output = (completed.stdout or "") + (completed.stderr or "")
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + f"\n... [truncated {len(output) - MAX_OUTPUT_CHARS} chars]"

        body = f"$ {command}\n{output}\n[exit {completed.returncode}]"
        return ToolResult(content=body, is_error=completed.returncode != 0)
