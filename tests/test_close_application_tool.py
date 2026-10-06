"""Unit tests for CloseApplicationTool and process termination workflows.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from core.agent import JarvisAgent
from core.permissions import PermissionManager
from models.ollama_client import OllamaClient
from tools.computer.applications import CloseApplicationTool, CRITICAL_SYSTEM_PROCESSES
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry


class TestCloseApplicationTool(unittest.TestCase):

    def setUp(self):
        self.tool = CloseApplicationTool()

    def test_schema_validity(self):
        schema = self.tool.get_parameters_schema()
        assert schema["type"] == "object"
        assert "app_name" in schema["required"]
        assert "app_name" in schema["properties"]

    def test_missing_app_name(self):
        result = self.tool.execute()
        assert not result.success
        assert "Parameter 'app_name' must be a non-empty string" in result.error

        result2 = self.tool.execute(app_name="")
        assert not result2.success
        assert "Parameter 'app_name' must be a non-empty string" in result2.error

    def test_critical_system_process_blocked(self):
        for proc_name in ["csrss", "csrss.exe", "svchost", "svchost.exe", "lsass", "winlogon"]:
            result = self.tool.execute(app_name=proc_name)
            assert not result.success
            assert "blocked by security policy" in result.error

    @patch("psutil.wait_procs")
    @patch("psutil.process_iter")
    def test_successful_close_graceful(self, mock_process_iter, mock_wait_procs):
        mock_proc = MagicMock()
        mock_proc.pid = 4321
        mock_proc.info = {"pid": 4321, "name": "notepad.exe"}
        mock_process_iter.return_value = [mock_proc]
        mock_wait_procs.return_value = ([mock_proc], [])

        result = self.tool.execute(app_name="notepad")

        assert result.success is True
        assert result.output["tool"] == "close_application"
        assert result.output["application"] == "Notepad"
        assert result.output["closed_pids"] == [4321]
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_not_called()

    @patch("psutil.wait_procs")
    @patch("psutil.process_iter")
    def test_close_fallback_to_kill_on_timeout(self, mock_process_iter, mock_wait_procs):
        mock_proc = MagicMock()
        mock_proc.pid = 9876
        mock_proc.info = {"pid": 9876, "name": "chrome.exe"}
        mock_process_iter.return_value = [mock_proc]
        mock_wait_procs.return_value = ([], [mock_proc])

        result = self.tool.execute(app_name="chrome")

        assert result.success is True
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert 9876 in result.output["closed_pids"]

    @patch("psutil.process_iter")
    def test_app_not_running(self, mock_process_iter):
        mock_process_iter.return_value = []

        result = self.tool.execute(app_name="nonexistent_program_xyz")

        assert not result.success
        assert "No running instance" in result.error

    @patch("psutil.wait_procs")
    @patch("psutil.process_iter")
    def test_packaged_app_aliases_matching(self, mock_process_iter, mock_wait_procs):
        # Calculator might be CalculatorApp.exe in Windows
        mock_calc = MagicMock()
        mock_calc.pid = 1111
        mock_calc.info = {"pid": 1111, "name": "CalculatorApp.exe"}
        mock_process_iter.return_value = [mock_calc]
        mock_wait_procs.return_value = ([mock_calc], [])

        result = self.tool.execute(app_name="calculator")
        assert result.success is True
        assert result.output["closed_pids"] == [1111]

        # WhatsApp might be WhatsApp.exe or WhatsApp.root.exe
        mock_wa = MagicMock()
        mock_wa.pid = 2222
        mock_wa.info = {"pid": 2222, "name": "WhatsApp.root.exe"}
        mock_process_iter.return_value = [mock_wa]
        mock_wait_procs.return_value = ([mock_wa], [])

        result_wa = self.tool.execute(app_name="whatsapp")
        assert result_wa.success is True
        assert result_wa.output["closed_pids"] == [2222]

    @patch("psutil.process_iter")
    def test_never_kills_own_pid(self, mock_process_iter):
        current_pid = os.getpid()
        mock_self = MagicMock()
        mock_self.pid = current_pid
        mock_self.info = {"pid": current_pid, "name": "python.exe"}
        mock_process_iter.return_value = [mock_self]

        result = self.tool.execute(app_name="python")
        assert not result.success
        mock_self.terminate.assert_not_called()


class TestAgentCloseApplicationIntegration(unittest.TestCase):

    def setUp(self):
        self.registry = ToolRegistry()
        self.close_tool = CloseApplicationTool()
        self.registry.register(self.close_tool)

        self.perms = PermissionManager()
        self.executor = ToolExecutor(registry=self.registry, permission_manager=self.perms)

        self.mock_client = MagicMock(spec=OllamaClient)
        self.mock_client.is_available.return_value = True
        self.mock_client.chat.return_value = {
            "success": True,
            "content": '{"thought": "None", "action": "respond", "response": "OK"}',
        }
        self.agent = JarvisAgent(
            client=self.mock_client,
            registry=self.registry,
            executor=self.executor,
        )

    @patch.object(CloseApplicationTool, "execute")
    def test_deterministic_close_command(self, mock_execute):
        from tools.base import ToolResult
        mock_execute.return_value = ToolResult(
            success=True,
            output={"tool": "close_application", "application": "Notepad", "message": "Notepad has been successfully closed."},
        )

        reply = self.agent.process_input("close notepad")
        assert "Notepad has been successfully closed." in reply
        mock_execute.assert_called_once_with(app_name="notepad")

    @patch.object(CloseApplicationTool, "execute")
    def test_llm_tool_call_close_application(self, mock_execute):
        from tools.base import ToolResult
        mock_execute.return_value = ToolResult(
            success=True,
            output={"tool": "close_application", "application": "Chrome", "message": "Chrome has been successfully closed."},
        )

        llm_response = """```json
{
  "thought": "User wants to close Chrome browser.",
  "action": "tool_call",
  "tool_name": "close_application",
  "parameters": {"app_name": "chrome"},
  "response": null
}
```"""
        self.mock_client.chat.return_value = {
            "success": True,
            "content": llm_response,
        }

        reply = self.agent.process_input("please terminate chrome browser")
        assert "Chrome has been successfully closed." in reply
        mock_execute.assert_called_once_with(app_name="chrome")
