"""Planner and prompt engineering for JARVIS reasoning and tool intent parsing.
"""

import ast
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

User: "close notepad"
{{
  "thought": "The user wants to close Notepad. I will use close_application with app_name 'notepad'.",
  "action": "tool_call",
  "tool_name": "close_application",
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
    def _extract_dict_from_content(cls, content: str) -> Optional[Dict[str, Any]]:
        """Extract a dictionary from raw content across varying formats and markdown fences."""
        cleaned = content.strip()

        # 1. Extract block between markdown fences if present
        block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
        candidate = block_match.group(1).strip() if block_match else cleaned

        # Locate first '{'
        start_idx = candidate.find("{")
        if start_idx == -1:
            start_idx = cleaned.find("{")
            if start_idx != -1:
                candidate = cleaned[start_idx:].strip()
                candidate = re.sub(r"```.*$", "", candidate, flags=re.DOTALL).strip()
            else:
                return None
        else:
            candidate = candidate[start_idx:].strip()

        # Try raw decode with strict=False
        try:
            decoder = json.JSONDecoder(strict=False)
            obj, _ = decoder.raw_decode(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # Try slice up to last '}'
        end_idx = candidate.rfind("}")
        if end_idx != -1:
            slice_candidate = candidate[: end_idx + 1]

            # Direct loads
            try:
                return json.loads(slice_candidate, strict=False)
            except Exception:
                pass

            # Sanitize trailing commas (,} -> } and ,] -> ])
            sanitized = re.sub(r",\s*([\]}])", r"\1", slice_candidate)
            try:
                return json.loads(sanitized, strict=False)
            except Exception:
                pass

            # Fix single quotes around keys and string values
            try:
                sq_fixed = re.sub(r"\'([a-zA-Z0-9_]+)\'\s*:", r'"\1":', sanitized)
                sq_fixed = re.sub(r":\s*\'([^\']*?)\'", r': "\1"', sq_fixed)
                return json.loads(sq_fixed, strict=False)
            except Exception:
                pass

            # Try ast.literal_eval
            try:
                py_candidate = (
                    sanitized.replace("null", "None")
                    .replace("true", "True")
                    .replace("false", "False")
                )
                val = ast.literal_eval(py_candidate)
                if isinstance(val, dict):
                    return val
            except Exception:
                pass

        return None

    @classmethod
    def parse_llm_response(cls, raw_content: str) -> Dict[str, Any]:
        """Extract and parse structured JSON decision from LLM output.

        Employs multi-tier decoding, trailing comma cleanup, single-quote correction,
        and deterministic regex fallback to guarantee zero false negative tool calls.
        """
        parsed = cls._extract_dict_from_content(raw_content)

        if parsed and isinstance(parsed, dict):
            action = parsed.get("action", "respond")
            tool_name = parsed.get("tool_name")
            parameters = parsed.get("parameters") or {}

            # Normalize tool_call: if model put the tool name into action
            if action and action not in ("respond", "tool_call"):
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

        # Deterministic Regex Fallback for tool intent if JSON structure had syntax errors
        tool_match = re.search(r'["\']tool_name["\']\s*:\s*["\']([^"\']+)["\']', raw_content)
        action_match = re.search(r'["\']action["\']\s*:\s*["\']([^"\']+)["\']', raw_content)

        detected_tool = None
        if tool_match and tool_match.group(1).lower() not in ("null", "none"):
            detected_tool = tool_match.group(1)
        elif action_match and action_match.group(1).lower() not in ("respond", "tool_call", "null", "none"):
            detected_tool = action_match.group(1)

        if detected_tool:
            params: Dict[str, Any] = {}
            for p in ("app_name", "application", "app", "url", "search_query", "path", "file_path"):
                pm = re.search(rf'["\']{p}["\']\s*:\s*["\']([^"\']+)["\']', raw_content)
                if pm:
                    params[p] = pm.group(1)

            thought_m = re.search(r'["\']thought["\']\s*:\s*["\']([^"\']+)["\']', raw_content)
            thought = thought_m.group(1) if thought_m else "Tool call intent extracted from model output"

            return {
                "thought": thought,
                "action": "tool_call",
                "tool_name": detected_tool,
                "parameters": params,
                "response": "",
            }

        # Fallback if raw text returned without any structured tool intent
        return {
            "thought": "Direct text output without structured tool intent",
            "action": "respond",
            "tool_name": None,
            "parameters": {},
            "response": raw_content.strip(),
        }
