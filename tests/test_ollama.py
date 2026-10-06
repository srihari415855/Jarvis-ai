"""Unit tests for OllamaClient abstraction.
"""

from unittest.mock import MagicMock, patch
import pytest
import requests

from models.ollama_client import OllamaClient


def test_ollama_unavailable_handled_gracefully():
    """6. Ollama unavailable is handled gracefully."""
    client = OllamaClient(base_url="http://localhost:11434")

    with patch("requests.get", side_effect=requests.RequestException("Connection refused")):
        assert client.is_available() is False
        assert client.list_models() == []

    with patch("requests.post", side_effect=requests.RequestException("Connection refused")):
        result = client.chat(messages=[{"role": "user", "content": "hi"}], model="test-model")
        assert result["success"] is False
        assert "Ollama connection error" in result["error"]


def test_ollama_missing_model_error():
    """Returns clear error if no model configured."""
    client = OllamaClient(base_url="http://localhost:11434", default_model=None)
    result = client.chat(messages=[{"role": "user", "content": "hi"}], model=None)

    assert result["success"] is False
    assert "No Ollama model configured" in result["error"]


def test_ollama_chat_success():
    """Ollama returns successful chat response."""
    client = OllamaClient(base_url="http://localhost:11434", default_model="gemma4:26b")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "gemma4:26b",
        "message": {"role": "assistant", "content": "I am Jarvis."},
    }

    with patch("requests.post", return_value=mock_resp):
        result = client.chat(messages=[{"role": "user", "content": "hello"}])
        assert result["success"] is True
        assert result["content"] == "I am Jarvis."
        assert result["model"] == "gemma4:26b"
