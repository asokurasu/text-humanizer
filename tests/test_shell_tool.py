"""Tests for the shell tool.""" 

from __future__ import annotations

import pytest

from claude_engineer.tools.base import ToolError
from claude_engineer.tools.shell import RunShell


def test_successful_command() -> None:
    out = RunShell().run(command="echo hello")
    assert "hello" in out.content
    assert out.is_error is False


def test_nonzero_exit_is_error() -> None:
    out = RunShell().run(command="sh -c 'exit 3'")
    assert out.is_error is True
    assert "exit 3" in out.content


def test_empty_command_raises() -> None:
    with pytest.raises(ToolError):
        RunShell().run(command="   ")
