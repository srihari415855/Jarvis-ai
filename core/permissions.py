"""Permission management, risk assessment, and auditing for JARVIS.
"""

from enum import Enum
import logging
from typing import Any, Callable, Dict, List, Optional
from tools.base import RiskLevel
from security.audit import audit_logger

logger = logging.getLogger("jarvis.security.permissions")


class PermissionDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class PermissionManager:
    """Evaluates risk, enforces least privilege policies, and records audit trails."""

    DANGEROUS_PATTERNS = [
        "rmdir", "del /", "format", "powershell -enc",
        "drop table", "shutdown", "reg add", "net user",
        "/etc/shadow", "chmod 777", "curl | bash"
    ]

    def __init__(
        self,
        confirmation_handler: Optional[Callable[[str, Dict[str, Any], RiskLevel], bool]] = None,
        auto_confirm_medium: bool = False,
    ):
        self._confirmation_handler = confirmation_handler or self._cli_prompt
        self.auto_confirm_medium = auto_confirm_medium
        self.audit_log: List[Dict[str, Any]] = []

    def _cli_prompt(self, tool_name: str, parameters: Dict[str, Any], risk: RiskLevel) -> bool:
        """Interactive CLI prompt for user authorization."""
        prompt_text = (
            f"\n[SECURITY PERMISSION] Tool '{tool_name}' (Risk: {risk.value}) "
            f"requests execution with arguments: {parameters}\n"
            f"Authorize execution? [y/N]: "
        )
        try:
            choice = input(prompt_text).strip().lower()
            return choice in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def validate_request_safety(self, tool_name: str, parameters: Dict[str, Any]) -> Optional[str]:
        """Check for destructive commands, credential extraction, or forbidden patterns."""
        param_str = str(parameters).lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in param_str:
                return f"Parameters contain prohibited pattern: '{pattern}'"
        return None

    def _record_audit(
        self,
        event_name: str,
        tool_name: str,
        parameters: Dict[str, Any],
        risk_level: RiskLevel,
        decision: PermissionDecision,
        reason: Optional[str] = None,
        log_level: int = logging.INFO,
    ) -> PermissionDecision:
        payload = {
            "tool_name": tool_name,
            "parameters": parameters,
            "risk_level": risk_level.value,
            "decision": decision.value,
        }
        if reason:
            payload["reason"] = reason

        entry = audit_logger.log_event(event_name, payload, level=log_level)
        self.audit_log.append(entry["details"])
        return decision

    def request_permission(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        risk_level: RiskLevel,
        is_registered: bool = True,
    ) -> PermissionDecision:
        """Evaluate policy, request confirmation if needed, and log decision."""
        # 1. Unknown tool -> DENY
        if not is_registered:
            logger.warning(f"DENY: Unregistered tool requested: '{tool_name}'")
            return self._record_audit(
                event_name="PERMISSION_DENIED",
                tool_name=tool_name,
                parameters=parameters,
                risk_level=risk_level,
                decision=PermissionDecision.DENY,
                reason="Unknown/unregistered tool",
                log_level=logging.WARNING,
            )

        # 2. Safety filter for destructive/malicious patterns
        safety_violation = self.validate_request_safety(tool_name, parameters)
        if safety_violation:
            logger.warning(f"DENY: Safety check failed for '{tool_name}': {safety_violation}")
            return self._record_audit(
                event_name="PERMISSION_DENIED",
                tool_name=tool_name,
                parameters=parameters,
                risk_level=risk_level,
                decision=PermissionDecision.DENY,
                reason=safety_violation,
                log_level=logging.WARNING,
            )

        # 3. Critical operations in Day 1 -> Default DENY
        if risk_level == RiskLevel.CRITICAL:
            logger.warning(f"DENY: Critical operation not allowed in Day 1: '{tool_name}'")
            return self._record_audit(
                event_name="PERMISSION_DENIED",
                tool_name=tool_name,
                parameters=parameters,
                risk_level=risk_level,
                decision=PermissionDecision.DENY,
                reason="Critical risk operations blocked in v0.1",
                log_level=logging.WARNING,
            )

        # 4. Low risk operations -> Auto ALLOW
        if risk_level == RiskLevel.LOW:
            decision = PermissionDecision.ALLOW
        elif risk_level == RiskLevel.MEDIUM and self.auto_confirm_medium:
            decision = PermissionDecision.ALLOW
        else:
            # Medium / High -> requires explicit confirmation
            confirmed = self._confirmation_handler(tool_name, parameters, risk_level)
            decision = PermissionDecision.ALLOW if confirmed else PermissionDecision.DENY

        event_name = "PERMISSION_GRANTED" if decision == PermissionDecision.ALLOW else "PERMISSION_DENIED"
        return self._record_audit(
            event_name=event_name,
            tool_name=tool_name,
            parameters=parameters,
            risk_level=risk_level,
            decision=decision,
        )
