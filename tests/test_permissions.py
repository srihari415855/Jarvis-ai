"""Unit tests for JARVIS permission manager and security policies.
"""

import pytest
from core.permissions import PermissionDecision, PermissionManager
from tools.base import RiskLevel


def test_permission_manager_allows_low_risk_tool():
    """1. Permission manager allows LOW-risk safe tool."""
    pm = PermissionManager()
    decision = pm.request_permission(
        tool_name="get_system_info",
        parameters={},
        risk_level=RiskLevel.LOW,
        is_registered=True,
    )
    assert decision == PermissionDecision.ALLOW
    assert len(pm.audit_log) == 1
    assert pm.audit_log[0]["decision"] == "ALLOW"


def test_unknown_tools_are_denied():
    """2. Unknown tools are denied."""
    pm = PermissionManager()
    decision = pm.request_permission(
        tool_name="unregistered_dangerous_tool",
        parameters={},
        risk_level=RiskLevel.HIGH,
        is_registered=False,
    )
    assert decision == PermissionDecision.DENY
    assert len(pm.audit_log) == 1
    assert pm.audit_log[0]["decision"] == "DENY"


def test_prohibited_dangerous_patterns_are_denied():
    """Destructive or dangerous parameter injections are denied."""
    pm = PermissionManager()
    decision = pm.request_permission(
        tool_name="some_tool",
        parameters={"cmd": "powershell -enc aW52b2tl..."},
        risk_level=RiskLevel.LOW,
        is_registered=True,
    )
    assert decision == PermissionDecision.DENY


def test_critical_risk_default_denied_in_day1():
    """CRITICAL risk operations default to DENY in Day 1."""
    pm = PermissionManager()
    decision = pm.request_permission(
        tool_name="kernel_patch",
        parameters={},
        risk_level=RiskLevel.CRITICAL,
        is_registered=True,
    )
    assert decision == PermissionDecision.DENY


def test_medium_risk_with_user_confirmation_allow():
    """MEDIUM risk with user confirmation ALLOW."""
    pm = PermissionManager(confirmation_handler=lambda tool, params, risk: True)
    decision = pm.request_permission(
        tool_name="launch_app",
        parameters={"app": "notepad"},
        risk_level=RiskLevel.MEDIUM,
        is_registered=True,
    )
    assert decision == PermissionDecision.ALLOW


def test_medium_risk_with_user_confirmation_deny():
    """MEDIUM risk with user confirmation DENY."""
    pm = PermissionManager(confirmation_handler=lambda tool, params, risk: False)
    decision = pm.request_permission(
        tool_name="launch_app",
        parameters={"app": "notepad"},
        risk_level=RiskLevel.MEDIUM,
        is_registered=True,
    )
    assert decision == PermissionDecision.DENY
