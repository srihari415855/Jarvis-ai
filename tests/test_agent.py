"""Unit tests for JarvisAgent integration and error resilience.
"""

from unittest.mock import MagicMock, patch
import pytest

from core.agent import JarvisAgent
from core.permissions import PermissionManager
from models.ollama_client import OllamaClient
from tools.base import BaseTool, RiskLevel, ToolResult
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry
from server.api import app
from fastapi.testclient import TestClient


class FailingTool(BaseTool):
    name = "failing_tool"
    description = "A tool that throws an unexpected exception."
    risk_level = RiskLevel.LOW

    def get_parameters_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, **kwargs):
        raise RuntimeError("Hardware failure simulation")


def test_tool_failure_does_not_crash_agent():
    """8. Tool failures don't crash the agent."""
    client = MagicMock(spec=OllamaClient)
    client.is_available.return_value = True
    client.chat.return_value = {
        "success": True,
        "content": '{"thought": "Run failing tool", "action": "tool_call", "tool_name": "failing_tool", "parameters": {}}',
    }

    registry = ToolRegistry()
    registry.register(FailingTool())

    pm = PermissionManager()
    executor = ToolExecutor(registry, pm)
    agent = JarvisAgent(client, registry, executor)

    # Should handle cleanly without raising RuntimeError
    response = agent.process_input("Trigger tool failure")
    assert "Action 'failing_tool' failed" in response


def test_agent_handles_offline_ollama():
    """Agent handles offline Ollama gracefully."""
    client = MagicMock(spec=OllamaClient)
    client.is_available.return_value = False
    client.base_url = "http://localhost:11434"

    registry = ToolRegistry()
    pm = PermissionManager()
    executor = ToolExecutor(registry, pm)
    agent = JarvisAgent(client, registry, executor)

    response = agent.process_input("hello")
    assert "Ollama daemon is currently not reachable" in response


def test_fastapi_health_endpoint():
    """16. FastAPI health endpoint returns expected status."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "jarvis"}
