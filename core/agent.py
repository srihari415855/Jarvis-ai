"""JarvisAgent core orchestrator with Phase 3 Computer Perception and Verification.
"""

import logging
import re
from typing import Any, Dict, List, Optional
from core.planner import Planner
from core.execution_loop import ExecutionStep, TaskExecutionLoop, TaskPlan
from models.ollama_client import OllamaClient
from tools.base import ToolResult
from tools.executor import ToolExecutor
from tools.registry import ToolRegistry
from security.audit import audit_logger

logger = logging.getLogger("jarvis.agent")


class JarvisAgent:
    """Core agent coordinating LLM reasoning, permissions, execution loops, and tools."""

    def __init__(
        self,
        client: OllamaClient,
        registry: ToolRegistry,
        executor: ToolExecutor,
        model: Optional[str] = None,
        execution_loop: Optional[TaskExecutionLoop] = None,
    ):
        self.client = client
        self.registry = registry
        self.executor = executor
        self.model = model
        self.execution_loop = execution_loop or TaskExecutionLoop(executor=executor)
        self.history: List[Dict[str, str]] = []
        self.max_history = 20

    def reset_context(self) -> None:
        """Clear conversation history."""
        self.history.clear()
        audit_logger.log_event("CONTEXT_RESET", {"message": "Agent conversation history cleared"})

    def _try_create_multi_step_plan(self, text: str) -> Optional[TaskPlan]:
        """Detect multi-step browser/computer intents and build a structured TaskPlan."""
        # 1. Open Chrome/browser and search for <query>
        search_pattern = (
            r"(?:open\s+(?:chrome|browser|google\s+chrome)\s+(?:and\s+)?search\s+(?:for\s+)?|"
            r"search\s+(?:for\s+)?)(['\"]?[^'\"]+?['\"]?)(?:\s+(?:on|in)\s+(?:chrome|google|browser))?$"
        )
        # Check compound "open chrome and search for ..." or "search for ... in chrome"
        compound_search = re.search(
            r"open\s+(?:chrome|browser|google\s+chrome)(?:,?\s+go\s+to\s+google)?,?\s+(?:and\s+)?search\s+(?:for\s+)?['\"]?([^'\"]+?)['\"]?(?:\s+and\s+tell\s+me.*)?$",
            text,
            re.IGNORECASE,
        )
        if compound_search:
            raw_query = compound_search.group(1).strip()
            # Clean trailing punctuation and whitespace
            raw_query = re.sub(r"[,;\.\?\!]+$", "", raw_query).strip()
            plan = TaskPlan(
                goal=f"Open Chrome and search for {raw_query}",
                steps=[
                    ExecutionStep(
                        step_number=1,
                        description="Open Chrome and navigate to Google",
                        tool_name="browser_navigate",
                        parameters={"url": "https://www.google.com"},
                        verification_type="browser_navigation",
                        verification_args={"url_pattern": "google"},
                    ),
                    ExecutionStep(
                        step_number=2,
                        description=f"Locate search field, enter '{raw_query}', and submit search",
                        tool_name="browser_interact",
                        parameters={
                            "action": "fill",
                            "target": {"selector": "textarea[name='q'], textarea[title='Search'], input[name='q']:not([type='hidden']), input[title='Search']"},
                            "value": raw_query,
                            "press_enter": True,
                        },
                        verification_type="browser_search",
                        verification_args={"query": raw_query},
                    ),
                ],
            )
            return plan

        # 2. Open Chrome and go to <url>
        nav_match = re.search(
            r"open\s+(?:chrome|browser|google\s+chrome)\s+(?:and\s+)?(?:go\s+to|navigate\s+to|open)\s+([a-zA-Z0-9\.\-\:\/]+)",
            text,
            re.IGNORECASE,
        )
        if nav_match:
            target_url = nav_match.group(1).strip().rstrip(".")
            domain_part = target_url.replace("https://", "").replace("http://", "").split("/")[0]
            plan = TaskPlan(
                goal=f"Open Chrome and go to {target_url}",
                steps=[
                    ExecutionStep(
                        step_number=1,
                        description=f"Open Chrome and navigate to {target_url}",
                        tool_name="browser_navigate",
                        parameters={"url": target_url},
                        verification_type="browser_navigation",
                        verification_args={"url_pattern": domain_part},
                    ),
                ],
            )
            return plan

        return None

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
        elif tool_name in ("open_application", "close_application") and isinstance(output, dict):
            return output.get("message") or f"{output.get('application', 'Application')} processed successfully."
        elif tool_name == "browser_navigate" and isinstance(output, dict):
            return f"Successfully navigated to {output.get('url')} (Title: '{output.get('title')}')."
        elif tool_name == "browser_interact" and isinstance(output, dict):
            return f"Browser action '{output.get('action')}' completed successfully."
        elif tool_name == "browser_inspect" and isinstance(output, dict):
            return f"Inspected page '{output.get('title')}' ({output.get('url')}). Found {output.get('elements_count')} elements."
        elif tool_name == "observe_screen" and isinstance(output, dict):
            return f"Active application: {output.get('application')} ('{output.get('active_window')}'). Found {output.get('elements_count')} UI elements."
        elif tool_name == "computer_control" and isinstance(output, dict):
            return f"Computer action '{output.get('action')}' completed: {output.get('status')}."
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

        # 1. Check for multi-step task intent (e.g. "Open Chrome and search for Python tutorials")
        multi_step_plan = self._try_create_multi_step_plan(text)
        if multi_step_plan:
            plan_res = self.execution_loop.execute_plan(multi_step_plan)
            assistant_reply = plan_res["message"]
            self.history.append({"role": "assistant", "content": assistant_reply})
            return assistant_reply

        # 2. Deterministic fast-path: check if query is an explicit application launch or close command
        app_match = re.match(r"^(?:open|launch|start|run)\s+([a-zA-Z0-9\s_\.\-]+)$", text, re.IGNORECASE)
        close_match = re.match(r"^(?:close|kill|terminate|stop|quit)\s+([a-zA-Z0-9\s_\.\-]+)$", text, re.IGNORECASE)
        app_tool = self.registry.get_tool("open_application")
        close_tool = self.registry.get_tool("close_application")

        if app_match and app_tool and hasattr(app_tool, "resolve_application"):
            target_app = app_match.group(1).strip()
            if app_tool.resolve_application(target_app) is not None:
                result = self.executor.execute("open_application", {"app_name": target_app})
                if result.metadata.get("permission_denied"):
                    assistant_reply = "Operation cancelled: Permission was denied for 'open_application'."
                else:
                    assistant_reply = self._format_tool_output("open_application", result)
                self.history.append({"role": "assistant", "content": assistant_reply})
                return assistant_reply

        if close_match and close_tool:
            target_app = close_match.group(1).strip()
            result = self.executor.execute("close_application", {"app_name": target_app})
            if result.metadata.get("permission_denied"):
                assistant_reply = "Operation cancelled: Permission was denied for 'close_application'."
            else:
                assistant_reply = self._format_tool_output("close_application", result)
            self.history.append({"role": "assistant", "content": assistant_reply})
            return assistant_reply

        # 3. Check if Ollama is available
        if not self.client.is_available():
            msg = (
                f"Ollama daemon is currently not reachable at '{self.client.base_url}'. "
                f"Please ensure Ollama is running (`ollama serve`)."
            )
            logger.warning(msg)
            return msg

        # 3. Construct system prompt with current tools
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
            if tool_name in ("open_application", "close_application") and not (parameters.get("app_name") or parameters.get("application") or parameters.get("app")):
                match = re.search(r"(?:open|launch|start|run|close|kill|terminate|stop|quit)\s+(.+)", text, re.IGNORECASE)
                if match:
                    parameters["app_name"] = match.group(1).strip()

            # Execute tool through authorized executor
            result: ToolResult = self.executor.execute(tool_name, parameters)

            if result.metadata.get("permission_denied"):
                assistant_reply = f"Operation cancelled: Permission was denied for '{tool_name}'."
            else:
                assistant_reply = self._format_tool_output(tool_name, result)
        else:
            # Deterministic fallback: check if user query is an explicit application launch or close command
            app_match = re.match(r"^(?:open|launch|start|run)\s+([a-zA-Z0-9\s_\.\-]+)$", text, re.IGNORECASE)
            close_match = re.match(r"^(?:close|kill|terminate|stop|quit)\s+([a-zA-Z0-9\s_\.\-]+)$", text, re.IGNORECASE)
            app_tool = self.registry.get_tool("open_application")
            close_tool = self.registry.get_tool("close_application")

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
            elif close_match and close_tool:
                target_app = close_match.group(1).strip()
                result = self.executor.execute("close_application", {"app_name": target_app})
                if result.metadata.get("permission_denied"):
                    assistant_reply = "Operation cancelled: Permission was denied for 'close_application'."
                else:
                    assistant_reply = self._format_tool_output("close_application", result)
            else:
                assistant_reply = plan.get("response") or raw_content

        # Save assistant message to history
        self.history.append({"role": "assistant", "content": assistant_reply})
        return assistant_reply
