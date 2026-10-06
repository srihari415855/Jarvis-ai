"""Planner and prompt engineering for JARVIS reasoning and tool intent parsing.
"""

import json
import re
from typing import Any, Dict, List, Optional


class Planner:
    """Handles system prompt construction and structured reasoning parsing."""

    SYSTEM_PROMPT_TEMPLATE = """You are JARVIS, an intelligent local-first personal AI assistant.
You assist the user by answering questions and executing actions through tools.

Available Tools:
{tools_schema}

Guidelines:
1. Always decide whether you need to use a tool or answer directly.
2. If you need a tool, you MUST specify "action": "tool_call", "tool_name", and the exact "parameters".
3. You must output your decision strictly in valid JSON format matching this schema:
{{
  "thought": "Your internal step-by-step reasoning",
  "action": "tool_call" or "respond",
  "tool_name": "name of tool if action is tool_call, else null",
  "parameters": {{"param_name": "value"}} or {{}},
  "response": "Text response to user if action is respond, else null"
}}

Example of tool execution:
User: "open notepad"
{{
  "thought": "The user wants to launch Notepad. I will use open_application with app_name 'notepad'.",
  "action": "tool_call",
  "tool_name": "open_application",
  "parameters": {{"app_name": "notepad"}},
  "response": null
}}

Do not include any text outside the JSON block. Output ONLY ONE JSON object.
"""

    @classmethod
    def build_system_prompt(cls, tool_schemas: List[Dict[str, Any]]) -> str:
        """Construct the system prompt incorporating registered tool schemas."""
        tools_formatted = json.dumps(tool_schemas, indent=2)
        return cls.SYSTEM_PROMPT_TEMPLATE.format(tools_schema=tools_formatted)

    @classmethod
    def parse_llm_response(cls, raw_content: str) -> Dict[str, Any]:
        """Extract and parse structured JSON decision from LLM output.

        Uses JSONDecoder.raw_decode to reliably parse the first valid JSON object,
        gracefully handling markdown fences, multiple JSON objects, or conversational wrapper text.
        """
        cleaned = raw_content.strip()

        # Handle markdown fenced code blocks ```json ... ```
        fence_match = re.search(r"```(?:json)?\s*(\{.*)", cleaned, re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1).strip()

        # Locate first '{' and decode
        idx = cleaned.find("{")
        if idx != -1:
            try:
                decoder = json.JSONDecoder()
                parsed, _ = decoder.raw_decode(cleaned[idx:])
                if isinstance(parsed, dict):
                    action = parsed.get("action", "respond")
                    tool_name = parsed.get("tool_name")
                    parameters = parsed.get("parameters") or {}

                    # Normalize tool_call: if model put the tool name into action
                    if action and action != "respond" and action != "tool_call":
                        if not tool_name:
                            tool_name = action
                        action = "tool_call"
                    elif tool_name and action != "respond":
                        action = "tool_call"

                    return {
                        "thought": parsed.get("thought", ""),
                        "action": action,
                        "tool_name": tool_name,
                        "parameters": parameters,
                        "response": parsed.get("response") or "",
                    }
            except json.JSONDecodeError:
                pass

        # Fallback if raw text returned without valid JSON
        return {
            "thought": "Direct text output without structured tool intent",
            "action": "respond",
            "tool_name": None,
            "parameters": {},
            "response": raw_content.strip(),
        }
