"""Integration tests for the voice pipeline with JarvisAgent and permission gating.
"""

from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from core.agent import JarvisAgent
from core.permissions import PermissionManager
from models.ollama_client import OllamaClient
from tools.computer.applications import GetSystemInfoTool
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry
from voice.voice_loop import VoiceLoop


def test_voice_integration_with_agent_and_tools():
    # Setup tools and permissions
    registry = ToolRegistry()
    registry.register(GetSystemInfoTool())

    permission_manager = PermissionManager()
    executor = ToolExecutor(registry=registry, permission_manager=permission_manager)

    mock_client = MagicMock(spec=OllamaClient)
    mock_client.is_available.return_value = True
    mock_client.chat.return_value = {
        "success": True,
        "content": '{"thought": "User wants system information", "action": "tool_call", "tool_name": "get_system_info", "parameters": {}}',
    }

    agent = JarvisAgent(client=mock_client, registry=registry, executor=executor)

    mock_mic = MagicMock()
    mock_mic.record_fixed_duration.return_value = np.zeros(16000, dtype=np.float32)

    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = "System info please"

    mock_tts = MagicMock()
    mock_tts.speak.return_value = True

    voice_loop = VoiceLoop(microphone=mock_mic, stt=mock_stt, agent=agent, tts=mock_tts)
    metrics = voice_loop.process_voice_turn(duration_seconds=2.0)

    assert metrics is not None
    assert metrics["user_text"] == "System info please"
    assert "Host System Information" in metrics["response_text"]
    mock_tts.speak.assert_called_once()
    assert "Host System Information" in mock_tts.speak.call_args[0][0]


def test_voice_integration_permission_enforcement():
    # Setup tools and permissions with blocked tool
    registry = ToolRegistry()
    registry.register(GetSystemInfoTool())

    permission_manager = PermissionManager()
    # Mock permission manager to deny
    permission_manager.request_permission = MagicMock(return_value="DENY")
    executor = ToolExecutor(registry=registry, permission_manager=permission_manager)

    mock_client = MagicMock(spec=OllamaClient)
    mock_client.is_available.return_value = True
    mock_client.chat.return_value = {
        "success": True,
        "content": '{"thought": "Get sys info", "action": "tool_call", "tool_name": "get_system_info", "parameters": {}}',
    }

    agent = JarvisAgent(client=mock_client, registry=registry, executor=executor)

    mock_mic = MagicMock()
    mock_mic.record_fixed_duration.return_value = np.zeros(16000, dtype=np.float32)

    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = "Check system specs"

    mock_tts = MagicMock()

    voice_loop = VoiceLoop(microphone=mock_mic, stt=mock_stt, agent=agent, tts=mock_tts)
    metrics = voice_loop.process_voice_turn(duration_seconds=2.0)

    assert metrics is not None
    assert "Permission was denied" in metrics["response_text"]
    mock_tts.speak.assert_called_once()
