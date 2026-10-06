"""Unit tests for JARVIS Day 1 safe tools and process verification.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.agent import JarvisAgent
from core.permissions import PermissionManager
from models.ollama_client import OllamaClient
from tools.base import BaseTool, RiskLevel, ToolResult
from tools.computer.applications import (
    GetSystemInfoTool,
    ListAllowedApplicationsTool,
    OpenApplicationTool,
    KNOWN_SYSTEM_APPS,
)
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry


def test_system_info_tool_returns_structured_data():
    """System info tool returns structured data without secrets."""
    tool = GetSystemInfoTool()
    result = tool.execute()

    assert result.success is True
    output = result.output
    assert isinstance(output, dict)
    assert "os" in output
    assert "cpu" in output
    assert "ram_total_gb" in output
    assert "ram_available_gb" in output
    assert "python_version" in output
    assert "jarvis_version" in output
    # Ensure sensitive fields are not present
    assert "password" not in output
    assert "token" not in output
    assert "key" not in output


def test_list_allowed_applications_tool():
    """Returns applications registered in common list."""
    tool = ListAllowedApplicationsTool()
    result = tool.execute()

    assert result.success is True
    allowed = result.output.get("allowed_applications", [])
    assert len(allowed) > 0
    names = [a["name"] for a in allowed]
    assert "Notepad" in names
    assert "Calculator" in names
    assert "File Explorer" in names


def test_notepad_resolution():
    """Notepad resolution to validated executable path."""
    tool = OpenApplicationTool()
    res = tool.resolve_application("notepad")
    assert res is not None
    target, display_name, method = res
    assert "notepad" in target.lower()
    assert display_name == "Notepad"


@patch("subprocess.Popen")
@patch("psutil.pid_exists", return_value=True)
def test_notepad_launch_and_pid(mock_pid_exists, mock_popen):
    """Notepad launch and PID returned."""
    mock_process = MagicMock()
    mock_process.pid = 54321
    mock_process.poll.return_value = None
    mock_popen.return_value = mock_process

    tool = OpenApplicationTool()
    result = tool.execute(app_name="notepad")

    assert result.success is True
    assert result.output["pid"] == 54321
    assert result.output["application"] == "Notepad"
    assert "Notepad launched successfully" in result.output["message"]


def test_invalid_application_rejection():
    """Invalid/non-existent application rejection."""
    tool = OpenApplicationTool()

    result = tool.execute(app_name="nonexistent_fake_app_xyz_999")
    assert result.success is False
    assert "could not be found" in result.error
    assert result.output["success"] is False


@patch("subprocess.Popen", side_effect=OSError("OS resource exhaustion"))
def test_subprocess_failure(mock_popen):
    """Subprocess failure handling."""
    tool = OpenApplicationTool()
    result = tool.execute(app_name="notepad")

    assert result.success is False
    assert "Failed to launch 'Notepad'" in result.error


@patch("subprocess.Popen")
def test_process_verification_immediate_exit(mock_popen):
    """Process verification detects immediate error exit."""
    mock_process = MagicMock()
    mock_process.pid = 11111
    mock_process.poll.return_value = 1  # Exited with error code 1
    mock_popen.return_value = mock_process

    tool = OpenApplicationTool()
    result = tool.execute(app_name="notepad")

    assert result.success is False
    assert "exited immediately with code 1" in result.error


def test_permission_manager_still_works():
    """PermissionManager still works with OpenApplicationTool."""
    registry = ToolRegistry()
    registry.register(OpenApplicationTool())

    pm_deny = PermissionManager(confirmation_handler=lambda t, p, r: False, auto_confirm_medium=False)
    executor_deny = ToolExecutor(registry=registry, permission_manager=pm_deny)
    res_deny = executor_deny.execute("open_application", {"app_name": "notepad"})
    # Low risk tools are auto-allowed by policy
    assert res_deny.success is True

    # Unregistered tool is strictly denied
    res_unknown = executor_deny.execute("unregistered_tool", {})
    assert res_unknown.success is False


def test_tool_failures_do_not_crash_agent():
    """Tool failures don't crash the agent."""
    client = MagicMock(spec=OllamaClient)
    client.is_available.return_value = True
    client.chat.return_value = {
        "success": True,
        "content": '{"thought": "Run failing tool", "action": "tool_call", "tool_name": "crashing_tool", "parameters": {}}',
    }

    class CrashingTool(BaseTool):
        name = "crashing_tool"
        description = "A tool that raises an unexpected exception."
        risk_level = RiskLevel.LOW
        def get_parameters_schema(self):
            return {"type": "object", "properties": {}}
        def execute(self, **kwargs):
            raise RuntimeError("Unexpected internal tool crash")

    registry = ToolRegistry()
    registry.register(CrashingTool())

    pm = PermissionManager()
    executor = ToolExecutor(registry=registry, permission_manager=pm)
    agent = JarvisAgent(client=client, registry=registry, executor=executor)

    response = agent.process_input("Run crashing tool")
    assert "Action 'crashing_tool' failed" in response
