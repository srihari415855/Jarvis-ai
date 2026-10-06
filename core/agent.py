"""JarvisAgent core orchestrator.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from core.planner import Planner
from models.ollama_client import OllamaClient
from tools.base import ToolResult
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry
from security.audit import audit_logger

logger = logging.getLogger("jarvis.agent")


class JarvisAgent:
    """Core agent coordinating LLM reasoning, permissions, and tool execution."""

    def __init__(
        self,
        client: OllamaClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
        model: Optional[str] = None,
    ):
        self.client = client
        self.registry = registry
        self.executor = executor
        self.model = model
        self.history: List[Dict[str, str]] = []
        self.max_history = 20

    def reset_context(self) -> None:
        """Clear conversation history."""
        self.history.clear()
        audit_logger.log_event("CONTEXT_RESET", {"message": "Agent conversation history cleared"})

    def _format_tool_output(self, tool_name: str, result: ToolResult) -> str:
        """Format raw tool result into a clear human-readable string."""
        if not result.success:
            reason = ""
            if isinstance(result.output, dict) and "error" in result.output:
                reason = f": {result.output['error']}"
            elif isinstance(result.output, dict) and "reason" in result.output:
                reason = f" ({result.output['reason']})"
            elif result.error:
                reason = f": {result.error}"
            return f"Action '{tool_name}' failed{reason}"

        output = result.output
        if tool_name == "get_system_info" and isinstance(output, dict):
            return (
                f"Host System Information:\n"
                f"  - OS: {output.get('os')}\n"
                f"  - CPU: {output.get('cpu')} ({output.get('cpu_count')} cores)\n"
                f"  - RAM: {output.get('ram_total_gb')} GB ({output.get('ram_percent_used')}% used, {output.get('ram_available_gb')} GB available)\n"
                f"  - Python: {output.get('python_version')}\n"
                f"  - Version: {output.get('jarvis_name')} v{output.get('jarvis_version')}"
            )
        elif tool_name == "list_allowed_applications" and isinstance(output, dict):
            apps = output.get("allowed_applications", [])
            lines = [f"  - {a.get('name')}: {a.get('description')}" for a in apps]
            note = f"\n\nNote: {output.get('note')}" if output.get("note") else ""
            return "Common Applications:\n" + "\n".join(lines) + note
        elif tool_name == "open_application" and isinstance(output, dict):
            return output.get("message") or f"{output.get('application', 'Application')} launched successfully."
        elif tool_name == "list_directory" and isinstance(output, dict):
            entries = output.get("entries", [])
            lines = [f"  {'[DIR] ' if e.get('is_dir') else '      '}{e.get('name')}" for e in entries]
            return f"Directory contents of {output.get('path')} ({len(entries)} items):\n" + "\n".join(lines)
        elif tool_name == "read_file" and isinstance(output, dict):
            return f"File content of {output.get('file_path')} ({output.get('lines_returned')} lines):\n\n{output.get('content')}"

        if isinstance(output, dict) and "message" in output:
            return output["message"]
        return str(output)

    def process_input(self, user_text: str) -> str:
        """Process a user query through reasoning, permission verification, and tools."""
        text = user_text.strip()
        if not text:
            return "Please provide a command or question."

        # Add user message to history
        self.history.append({"role": "user", "content": text})
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        audit_logger.log_event("USER_REQUEST", {"query": text})

        # Check if Ollama is available
        if not self.client.is_available():
            msg = (
                f"Ollama daemon is currently not reachable at '{self.client.base_url}'. "
                f"Please ensure Ollama is running (`ollama serve`)."
            )
            logger.warning(msg)
            return msg

        # Construct system prompt with current tools
        schemas = self.registry.get_schemas()
        system_prompt = Planner.build_system_prompt(schemas)

        # Call local LLM
        response_data = self.client.chat(
            messages=self.history,
            model=self.model,
            system_prompt=system_prompt,
        )

        if not response_data.get("success"):
            err = response_data.get("error", "Unknown LLM error")
            logger.error(f"LLM inference error: {err}")
            return f"I encountered an error communicating with the local model: {err}"

        raw_content = response_data.get("content", "")
        plan = Planner.parse_llm_response(raw_content)

        audit_logger.log_event("AGENT_DECISION", {
            "thought": plan.get("thought"),
            "action": plan.get("action"),
            "tool_name": plan.get("tool_name"),
        })

        # Handle tool call if requested by model
        if plan.get("action") == "tool_call" and plan.get("tool_name"):
            tool_name = plan["tool_name"]
            parameters = plan.get("parameters") or {}

            # Parameter fallback: dynamically extract app name if omitted by LLM
            if tool_name == "open_application" and not (parameters.get("app_name") or parameters.get("application") or parameters.get("app")):
                match = re.search(r"(?:open|launch|start|run)\s+(.+)", text, re.IGNORECASE)
                if match:
                    parameters["app_name"] = match.group(1).strip()

            # Execute tool through authorized executor
            result: ToolResult = self.executor.execute(tool_name, parameters)

            if result.metadata.get("permission_denied"):
                assistant_reply = f"Operation cancelled: Permission was denied for '{tool_name}'."
            else:
                assistant_reply = self._format_tool_output(tool_name, result)
        else:
            # Deterministic fallback: check if user query is an explicit application launch command
            # that can be resolved on the system (e.g. 'open chrome', 'launch brave', 'open notepad')
            app_match = re.match(r"^(?:open|launch|start|run)\s+([a-zA-Z0-9\s_\.\-]+)$", text, re.IGNORECASE)
            app_tool = self.registry.get_tool("open_application")
            if app_match and app_tool and hasattr(app_tool, "resolve_application"):
                target_app = app_match.group(1).strip()
                if app_tool.resolve_application(target_app) is not None:
                    result = self.executor.execute("open_application", {"app_name": target_app})
                    if result.metadata.get("permission_denied"):
                        assistant_reply = "Operation cancelled: Permission was denied for 'open_application'."
                    else:
                        assistant_reply = self._format_tool_output("open_application", result)
                else:
                    assistant_reply = plan.get("response") or raw_content
            else:
                assistant_reply = plan.get("response") or raw_content

        # Save assistant message to history
        self.history.append({"role": "assistant", "content": assistant_reply})
        return assistant_reply
