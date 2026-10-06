"""Filesystem tools for JARVIS.

Provides safe directory listing and text file inspection with path sanitization.
"""

import os
from pathlib import Path
import logging
from typing import Any, Dict, List, Optional

from tools.base import BaseTool, RiskLevel, ToolResult
from security.audit import audit_logger

logger = logging.getLogger("jarvis.tools.filesystem")


class ListDirectoryTool(BaseTool):
    """Safely list entries in a directory."""

    name: str = "list_directory"
    description: str = (
        "List files and folders in a specified directory path. "
        "Defaults to the current working directory if path is not specified."
    )
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list (e.g. '.' or 'D:/AI Agent/Jarvis').",
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        dir_path_str = kwargs.get("path") or "."
        target_path = Path(dir_path_str).resolve()

        if not target_path.exists():
            return ToolResult(
                success=False,
                error=f"Directory does not exist: '{dir_path_str}'",
            )

        if not target_path.is_dir():
            return ToolResult(
                success=False,
                error=f"Path is not a directory: '{dir_path_str}'",
            )

        try:
            entries: List[Dict[str, Any]] = []
            for item in sorted(target_path.iterdir()):
                try:
                    stat = item.stat()
                    entries.append({
                        "name": item.name,
                        "is_dir": item.is_dir(),
                        "size_bytes": stat.st_size if not item.is_dir() else None,
                    })
                except (PermissionError, OSError):
                    entries.append({
                        "name": item.name,
                        "is_dir": item.is_dir(),
                        "size_bytes": None,
                        "restricted": True,
                    })

            audit_logger.log_event("FILESYSTEM_LIST", {"path": str(target_path), "count": len(entries)})
            return ToolResult(
                success=True,
                output={
                    "path": str(target_path),
                    "total_entries": len(entries),
                    "entries": entries[:100],  # cap at 100 entries
                },
            )
        except Exception as exc:
            logger.error(f"Failed to list directory '{target_path}': {exc}")
            return ToolResult(
                success=False,
                error=f"Error listing directory: {str(exc)}",
            )


class ReadFileTool(BaseTool):
    """Safely read lines from a local text file."""

    name: str = "read_file"
    description: str = (
        "Read contents of a text file with safety limits on size and line count."
    )
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False

    MAX_BYTES = 500_000  # 500 KB limit
    MAX_LINES = 200

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["file_path"],
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read.",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum number of lines to read (default: 50, max: 200).",
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        file_path_str = kwargs.get("file_path")
        if not file_path_str:
            return ToolResult(
                success=False,
                error="Parameter 'file_path' is required.",
            )

        target_path = Path(file_path_str).resolve()
        max_lines = min(int(kwargs.get("max_lines") or 50), self.MAX_LINES)

        if not target_path.exists():
            return ToolResult(
                success=False,
                error=f"File not found: '{file_path_str}'",
            )

        if not target_path.is_file():
            return ToolResult(
                success=False,
                error=f"Path is not a regular file: '{file_path_str}'",
            )

        # Size check
        size = target_path.stat().st_size
        if size > self.MAX_BYTES:
            return ToolResult(
                success=False,
                error=f"File exceeds maximum allowed size ({size} bytes > {self.MAX_BYTES} bytes).",
            )

        try:
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [f.readline() for _ in range(max_lines)]
                content = "".join([l for l in lines if l])

            audit_logger.log_event("FILESYSTEM_READ", {"file": str(target_path), "lines_read": len(lines)})
            return ToolResult(
                success=True,
                output={
                    "file_path": str(target_path),
                    "lines_returned": len(lines),
                    "content": content,
                },
            )
        except Exception as exc:
            logger.error(f"Failed to read file '{target_path}': {exc}")
            return ToolResult(
                success=False,
                error=f"Failed to read file: {str(exc)}",
            )
