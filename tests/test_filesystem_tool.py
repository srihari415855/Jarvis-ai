"""Unit tests for Filesystem tools (ListDirectoryTool, ReadFileTool).
"""

from pathlib import Path
import pytest

from tools.filesystem.filesystem import ListDirectoryTool, ReadFileTool
from tools.base import RiskLevel


def test_list_directory_tool_schema():
    tool = ListDirectoryTool()
    assert tool.name == "list_directory"
    assert tool.risk_level == RiskLevel.LOW
    schema = tool.to_schema()
    assert "properties" in schema["parameters"]


def test_list_directory_tool_execution(tmp_path):
    # Create temp files
    (tmp_path / "file1.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "subdir").mkdir()

    tool = ListDirectoryTool()
    result = tool.execute(path=str(tmp_path))

    assert result.success is True
    assert result.output["total_entries"] == 2
    names = [e["name"] for e in result.output["entries"]]
    assert "file1.txt" in names
    assert "subdir" in names


def test_list_directory_tool_invalid_path():
    tool = ListDirectoryTool()
    result = tool.execute(path="non_existent_directory_12345")
    assert result.success is False
    assert "Directory does not exist" in result.error


def test_read_file_tool_schema():
    tool = ReadFileTool()
    assert tool.name == "read_file"
    assert tool.risk_level == RiskLevel.LOW
    schema = tool.to_schema()
    assert "file_path" in schema["parameters"]["required"]


def test_read_file_tool_execution(tmp_path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    tool = ReadFileTool()
    result = tool.execute(file_path=str(test_file), max_lines=2)

    assert result.success is True
    assert result.output["lines_returned"] == 2
    assert "line 1\nline 2\n" in result.output["content"]


def test_read_file_tool_non_existent():
    tool = ReadFileTool()
    result = tool.execute(file_path="non_existent_file_98765.txt")
    assert result.success is False
    assert "File not found" in result.error


def test_read_file_tool_exceeds_size(tmp_path, monkeypatch):
    large_file = tmp_path / "large.txt"
    large_file.write_text("sample content", encoding="utf-8")

    tool = ReadFileTool()
    monkeypatch.setattr(tool, "MAX_BYTES", 5)

    result = tool.execute(file_path=str(large_file))
    assert result.success is False
    assert "File exceeds maximum allowed size" in result.error
