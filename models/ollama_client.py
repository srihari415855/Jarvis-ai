"""Ollama API client abstraction for local LLM inference.
"""

import json
import logging
from typing import Any, Dict, List, Optional
import requests
from config.settings import settings

logger = logging.getLogger("jarvis.models.ollama")


class OllamaClient:
    """Client for communicating with the local Ollama daemon."""

    def __init__(self, base_url: Optional[str] = None, default_model: Optional[str] = settings.OLLAMA_MODEL):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.default_model = default_model
        self.timeout = 60

    def is_available(self) -> bool:
        """Check if local Ollama daemon is reachable."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> List[str]:
        """List locally installed Ollama models."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [m.get("name") for m in data.get("models", []) if "name" in m]
        except requests.RequestException as exc:
            logger.warning(f"Failed to fetch model list from Ollama: {exc}")
        return []

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        format_json: bool = False,
    ) -> Dict[str, Any]:
        """Send chat completion request to Ollama.

        Returns:
            Dict containing 'success', 'content', 'model', and optional 'error'.
        """
        target_model = model or self.default_model
        if not target_model:
            return {
                "success": False,
                "content": "",
                "error": "No Ollama model configured. Set OLLAMA_MODEL in .env or specify a model.",
            }

        payload_messages = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        payload_messages.extend(messages)

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": payload_messages,
            "stream": False,
        }
        if format_json:
            payload["format"] = "json"

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            message = data.get("message", {})
            return {
                "success": True,
                "content": message.get("content", ""),
                "model": data.get("model", target_model),
                "raw": data,
            }
        except requests.RequestException as exc:
            err_msg = f"Ollama connection error at '{self.base_url}': {str(exc)}"
            logger.error(err_msg)
            return {
                "success": False,
                "content": "",
                "error": err_msg,
                "model": target_model,
            }
