from __future__ import annotations

import os 
from pathlib import Path 

import pytest

from claude_engineer.tools.base import ToolError
from claude_engineer.tools.fs import ListDir, ReadFile, WriteFile


def test_write_then_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    WriteFile().run(path="hello.txt", content="hi there")
    result = ReadFile().run(path="hello.txt")
    assert result.content == "hi there"


def test_read_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ToolError):
        ReadFile().run(path="does-not-exist.txt")


def test_list_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    out = ListDir().run(path=".")
    assert "a.txt" in out.content
    assert "sub/" in out.content


def test_write_creates_parents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    WriteFile().run(path="deep/nested/file.txt", content="ok")
    assert (tmp_path / "deep" / "nested" / "file.txt").read_text() == "ok"
