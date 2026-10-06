"""Tool executor that routes through the permission manager before executing.
"""

import logging
from typing import Any, Dict
from core.permissions import PermissionDecision, PermissionManager
from tools.base import RiskLevel, ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger("jarvis.tools.executor")


class ToolExecutor:
    """Dispatches tool execution only after obtaining permission approval."""

    def __init__(self, registry: ToolRegistry, permission_manager: PermissionManager):
        self.registry = registry
        self.permission_manager = permission_manager

    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> ToolResult:
        """Verify permission and execute tool if allowed."""
        tool = self.registry.get_tool(tool_name)

        # 1. Handle unknown/unregistered tools
        if not tool:
            self.permission_manager.request_permission(
                tool_name=tool_name,
                parameters=parameters,
                risk_level=RiskLevel.HIGH,
                is_registered=False,
            )
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' is not in the allowed tool registry.",
                output={"success": False, "reason": "Unknown tool"},
            )

        # 2. Check permission through the manager
        decision = self.permission_manager.request_permission(
            tool_name=tool_name,
            parameters=parameters,
            risk_level=tool.risk_level,
            is_registered=True,
        )

        if decision != PermissionDecision.ALLOW:
            logger.info(f"Execution of '{tool_name}' blocked by permission policy.")
            return ToolResult(
                success=False,
                error=f"Execution of '{tool_name}' denied by permission policy.",
                metadata={"permission_denied": True},
            )

        # 3. Execute authorized tool
        logger.info(f"Executing authorized tool '{tool_name}' with parameters: {parameters}")
        try:
            return tool.execute(**parameters)
        except Exception as exc:
            logger.error(f"Error executing '{tool_name}': {str(exc)}")
            return ToolResult(
                success=False,
                error=f"Tool execution failed: {str(exc)}",
            )
