"""Unit tests for OllamaClient.
"""

import unittest
from unittest.mock import MagicMock, patch
import requests
from models.ollama_client import OllamaClient


class TestOllamaClient(unittest.TestCase):

    def setUp(self):
        self.client = OllamaClient(base_url="http://localhost:11434", default_model="test-model")

    @patch("requests.get")
    def test_is_available_true(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        self.assertTrue(self.client.is_available())
        mock_get.assert_called_once_with("http://localhost:11434/api/tags", timeout=3)

    @patch("requests.get")
    def test_is_available_false_on_exception(self, mock_get):
        mock_get.side_effect = requests.RequestException("Connection refused")
        self.assertFalse(self.client.is_available())

    @patch("requests.get")
    def test_list_models_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3:latest"},
                {"name": "mistral:latest"},
            ]
        }
        mock_get.return_value = mock_response

        models = self.client.list_models()
        self.assertEqual(models, ["llama3:latest", "mistral:latest"])

    @patch("requests.post")
    def test_chat_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model": "test-model",
            "message": {"role": "assistant", "content": "Hello! I am Jarvis."},
        }
        mock_post.return_value = mock_response

        result = self.client.chat(
            messages=[{"role": "user", "content": "Hi"}],
            system_prompt="You are helpful.",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["content"], "Hello! I am Jarvis.")
        self.assertEqual(result["model"], "test-model")

    @patch("requests.post")
    def test_chat_failure(self, mock_post):
        mock_post.side_effect = requests.RequestException("Ollama down")

        result = self.client.chat(messages=[{"role": "user", "content": "Hi"}])
        self.assertFalse(result["success"])
        self.assertIn("Ollama down", result["error"])


if __name__ == "__main__":
    unittest.main()
