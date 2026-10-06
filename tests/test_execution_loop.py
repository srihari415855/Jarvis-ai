"""Unit tests for TaskExecutionLoop and retry handling.
"""

from unittest.mock import MagicMock
import pytest

from core.execution_loop import ExecutionStep, TaskExecutionLoop, TaskPlan
from tools.base import ToolResult
from tools.computer.verification import VerificationResult


def test_task_plan_successful_execution():
    mock_executor = MagicMock()
    mock_executor.execute.return_value = ToolResult(success=True, output={"status": "ok"})

    mock_verifier = MagicMock()
    mock_verifier.verify_browser_navigation.return_value = VerificationResult(
        verified=True, condition="nav", message="Navigation verified."
    )

    loop = TaskExecutionLoop(
        executor=mock_executor,
        verifier=mock_verifier,
        max_retries=2,
    )

    plan = TaskPlan(
        goal="Test successful flow",
        steps=[
            ExecutionStep(
                step_number=1,
                description="Navigate to test site",
                tool_name="browser_navigate",
                parameters={"url": "https://example.com"},
                verification_type="browser_navigation",
            )
        ],
    )

    res = loop.execute_plan(plan)
    assert res["success"] is True
    assert res["status"] == "COMPLETED"
    assert len(res["history"]) == 1
    mock_executor.execute.assert_called_once()


def test_task_plan_permission_denied_stops_loop():
    mock_executor = MagicMock()
    mock_executor.execute.return_value = ToolResult(
        success=False,
        error="Permission denied",
        metadata={"permission_denied": True},
    )

    loop = TaskExecutionLoop(executor=mock_executor, max_retries=2)

    plan = TaskPlan(
        goal="Blocked task",
        steps=[
            ExecutionStep(
                step_number=1,
                description="High risk action",
                tool_name="dangerous_tool",
                parameters={},
            ),
            ExecutionStep(
                step_number=2,
                description="Should not run",
                tool_name="another_tool",
                parameters={},
            ),
        ],
    )

    res = loop.execute_plan(plan)
    assert res["success"] is False
    assert res["status"] == "PERMISSION_DENIED"
    assert mock_executor.execute.call_count == 1  # Did not run step 2


def test_task_plan_retry_limit_enforced():
    mock_executor = MagicMock()
    # Always fails
    mock_executor.execute.return_value = ToolResult(
        success=False,
        error="Simulated network failure",
    )

    loop = TaskExecutionLoop(executor=mock_executor, max_retries=2)

    plan = TaskPlan(
        goal="Failing task",
        steps=[
            ExecutionStep(
                step_number=1,
                description="Network call",
                tool_name="browser_navigate",
                parameters={"url": "https://example.com"},
            )
        ],
    )

    res = loop.execute_plan(plan)
    assert res["success"] is False
    assert res["status"] == "ACTION_FAILED"
    # Initial attempt + 2 retries = 3 total attempts
    assert mock_executor.execute.call_count == 3


def test_task_plan_verification_retry_and_stop():
    mock_executor = MagicMock()
    mock_executor.execute.return_value = ToolResult(success=True, output={})

    mock_verifier = MagicMock()
    # Always fails verification
    mock_verifier.verify_browser_navigation.return_value = VerificationResult(
        verified=False,
        condition="nav_failed",
        message="Did not reach target URL",
    )

    loop = TaskExecutionLoop(
        executor=mock_executor,
        verifier=mock_verifier,
        max_retries=2,
    )

    plan = TaskPlan(
        goal="Unverifiable navigation",
        steps=[
            ExecutionStep(
                step_number=1,
                description="Navigate and verify",
                tool_name="browser_navigate",
                parameters={"url": "https://example.com"},
                verification_type="browser_navigation",
            )
        ],
    )

    res = loop.execute_plan(plan)
    assert res["success"] is False
    assert res["status"] == "VERIFICATION_FAILED"
    assert mock_executor.execute.call_count == 3
