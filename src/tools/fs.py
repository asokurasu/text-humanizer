"""File system tools: read, write, list."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_engineer.tools.base import Tool, ToolError, ToolResult


MAX_READ_BYTES = 1_000_000  # 1 MB cap to keep tool results reasonable


def _resolve(path: str) -> Path:
    """Resolve a user-supplied path against the current working directory."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()


class ReadFile(Tool):
    name = "read_file"
    description = (
        "Read the contents of a text file at the given path. "
        "Paths may be absolute or relative to the current working directory."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read.",
            },
        },
        "required": ["path"],
    }

    def run(self, path: str) -> ToolResult:
        target = _resolve(path)
        if not target.exists():
            raise ToolError(f"File not found: {target}")
        if target.is_dir():
            raise ToolError(f"Path is a directory, not a file: {target}")
        try:
            data = target.read_bytes()
        except OSError as exc:
            raise ToolError(f"Could not read {target}: {exc}") from exc

        if len(data) > MAX_READ_BYTES:
            raise ToolError(
                f"File is too large ({len(data)} bytes). "
                f"Read up to {MAX_READ_BYTES} bytes at a time."
            )

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ToolError(f"{target} does not look like UTF-8 text.")

        return ToolResult(content=text)


class WriteFile(Tool):
    name = "write_file"
    description = (
        "Create or overwrite a text file with the given content. "
        "Intermediate directories are created as needed."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to write."},
            "content": {
                "type": "string",
                "description": "Full text content to write to the file.",
            },
        },
        "required": ["path", "content"],
    }

    def run(self, path: str, content: str) -> ToolResult:
        target = _resolve(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise ToolError(f"Could not write {target}: {exc}") from exc

        return ToolResult(content=f"Wrote {len(content)} chars to {target}")


class ListDir(Tool):
    name = "list_dir"
    description = "List the immediate contents of a directory."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory to list. Defaults to the current working directory.",
            },
        },
    }

    def run(self, path: str = ".") -> ToolResult:
        target = _resolve(path)
        if not target.exists():
            raise ToolError(f"Directory not found: {target}")
        if not target.is_dir():
            raise ToolError(f"Not a directory: {target}")

        entries = []
        for child in sorted(target.iterdir()):
            marker = "/" if child.is_dir() else ""
            entries.append(f"{child.name}{marker}")

        if not entries:
            return ToolResult(content=f"{target} is empty.")

        listing = "\n".join(entries)
        return ToolResult(content=f"{target}:\n{listing}")
