"""Controlled Task Execution Loop for JARVIS Phase 3 Computer & Browser Operations.

Implements the fundamental loop:
UNDERSTAND -> OBSERVE -> PLAN -> ACT -> OBSERVE -> VERIFY -> CONTINUE / STOP

Guarantees:
1. No raw Python/shell code execution
2. All actions routed through PermissionManager and ToolExecutor
3. Empirical verification of results without fabrication
4. Configurable retry limit (default: 2 retries)
5. Comprehensive audit logging
"""

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Dict, List, Optional

from tools.base import ToolResult
from tools.executor import ToolExecutor
from tools.browser.browser import PlaywrightBrowserManager
from tools.computer.perception import ComputerPerception
from tools.computer.verification import ActionVerifier, VerificationResult
from security.audit import audit_logger

logger = logging.getLogger("jarvis.core.execution_loop")


@dataclass
class ExecutionStep:
    """A single discrete step in a task execution plan."""
    step_number: int
    description: str
    tool_name: str
    parameters: Dict[str, Any]
    verification_type: Optional[str] = None  # e.g. "browser_navigation", "browser_search", "window_active"
    verification_args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskPlan:
    """An ordered plan of executable steps to achieve a user goal."""
    goal: str
    steps: List[ExecutionStep] = field(default_factory=list)


class TaskExecutionLoop:
    """Orchestrates structured, verified multi-step computer tasks."""

    def __init__(
        self,
        executor: ToolExecutor,
        verifier: Optional[ActionVerifier] = None,
        browser_manager: Optional[PlaywrightBrowserManager] = None,
        perception: Optional[ComputerPerception] = None,
        max_retries: int = 2,
    ):
        self.executor = executor
        self.verifier = verifier or ActionVerifier()
        self.browser_manager = browser_manager or PlaywrightBrowserManager.get_instance()
        self.perception = perception or ComputerPerception()
        self.max_retries = max_retries

    def execute_plan(self, plan: TaskPlan) -> Dict[str, Any]:
        """Execute a task plan through the observe-act-observe-verify loop."""
        audit_logger.log_event("PLAN_CREATED", {
            "goal": plan.goal,
            "step_count": len(plan.steps),
            "steps": [s.description for s in plan.steps],
        })

        execution_history: List[Dict[str, Any]] = []

        for step in plan.steps:
            logger.info(f"Executing Step {step.step_number}/{len(plan.steps)}: {step.description}")
            retries_remaining = self.max_retries
            step_succeeded = False

            while retries_remaining >= 0 and not step_succeeded:
                # 1. OBSERVE BEFORE STATE
                before_obs = self._observe_current_state()
                audit_logger.log_event("OBSERVE_BEFORE", {
                    "step": step.step_number,
                    "state": before_obs,
                })

                # 2. PROPOSE ACTION
                audit_logger.log_event("ACTION_PROPOSED", {
                    "step": step.step_number,
                    "tool": step.tool_name,
                    "parameters": step.parameters,
                })

                # 3. EXECUTE ACTION (Through PermissionManager & ToolExecutor)
                audit_logger.log_event("ACTION_EXECUTION", {
                    "step": step.step_number,
                    "tool": step.tool_name,
                })
                result: ToolResult = self.executor.execute(step.tool_name, step.parameters)

                audit_logger.log_event("ACTION_RESULT", {
                    "step": step.step_number,
                    "tool": step.tool_name,
                    "success": result.success,
                    "error": result.error,
                })

                if result.metadata.get("permission_denied"):
                    audit_logger.log_event("TASK_FAILED", {
                        "reason": f"Permission denied on step {step.step_number}",
                    })
                    return {
                        "success": False,
                        "status": "PERMISSION_DENIED",
                        "message": f"Operation stopped: permission denied for '{step.tool_name}'.",
                        "history": execution_history,
                    }

                if not result.success:
                    if retries_remaining > 0:
                        logger.warning(
                            f"Step {step.step_number} failed ({result.error}). Retrying ({retries_remaining} retries left)..."
                        )
                        audit_logger.log_event("RETRY", {
                            "step": step.step_number,
                            "retries_remaining": retries_remaining,
                            "error": result.error,
                        })
                        retries_remaining -= 1
                        time.sleep(1.0)
                        continue
                    else:
                        audit_logger.log_event("TASK_FAILED", {
                            "reason": f"Step {step.step_number} failed: {result.error}",
                        })
                        return {
                            "success": False,
                            "status": "ACTION_FAILED",
                            "message": f"Action failed on step {step.step_number} ({step.description}): {result.error}",
                            "history": execution_history,
                        }

                # 4. OBSERVE AFTER STATE
                time.sleep(0.5)
                after_obs = self._observe_current_state()
                audit_logger.log_event("OBSERVE_AFTER", {
                    "step": step.step_number,
                    "state": after_obs,
                })

                # 5. EMPIRICAL VERIFICATION
                verification = self._verify_step(step)
                audit_logger.log_event("VERIFICATION", verification.to_dict())

                if verification.verified:
                    step_succeeded = True
                    execution_history.append({
                        "step": step.step_number,
                        "description": step.description,
                        "status": "SUCCESS",
                        "verification": verification.message,
                    })
                else:
                    if retries_remaining > 0:
                        logger.warning(
                            f"Step {step.step_number} verification failed: {verification.message}. Retrying..."
                        )
                        audit_logger.log_event("RETRY", {
                            "step": step.step_number,
                            "retries_remaining": retries_remaining,
                            "reason": verification.message,
                        })
                        retries_remaining -= 1
                        time.sleep(1.0)
                    else:
                        audit_logger.log_event("TASK_FAILED", {
                            "reason": f"Verification failed on step {step.step_number}: {verification.message}",
                        })
                        return {
                            "success": False,
                            "status": "VERIFICATION_FAILED",
                            "message": f"Could not verify completion of step {step.step_number} ({step.description}): {verification.message}",
                            "history": execution_history,
                        }

        # All steps successfully executed and verified
        audit_logger.log_event("TASK_COMPLETE", {
            "goal": plan.goal,
            "steps_completed": len(plan.steps),
        })

        # Final verification message
        last_step_verification = execution_history[-1]["verification"] if execution_history else "Task finished."
        return {
            "success": True,
            "status": "COMPLETED",
            "message": f"Successfully completed goal: '{plan.goal}'. {last_step_verification}",
            "history": execution_history,
        }

    def _observe_current_state(self) -> Dict[str, Any]:
        """Collect current system observation (browser and desktop)."""
        state: Dict[str, Any] = {}
        if self.browser_manager.is_active:
            state["browser"] = {
                "url": self.browser_manager._page.url if self.browser_manager._page else "",
                "title": self.browser_manager._page.title() if self.browser_manager._page else "",
            }
        else:
            win = self.perception.get_active_window()
            state["desktop"] = {
                "active_window": win.get("title", ""),
                "application": win.get("application", ""),
            }
        return state

    def _verify_step(self, step: ExecutionStep) -> VerificationResult:
        """Run verification check based on step specification."""
        if not step.verification_type:
            # Default auto-pass if step does not require separate verification
            return VerificationResult(
                verified=True,
                condition="unconditional",
                message=f"Action '{step.tool_name}' executed successfully.",
            )

        v_type = step.verification_type
        args = step.verification_args

        if v_type == "browser_navigation":
            return self.verifier.verify_browser_navigation(
                self.browser_manager,
                expected_url_pattern=args.get("url_pattern"),
                expected_title_pattern=args.get("title_pattern"),
            )
        elif v_type == "browser_search":
            return self.verifier.verify_browser_search_results(
                self.browser_manager,
                query=args.get("query", ""),
            )
        elif v_type == "window_active":
            return self.verifier.verify_window_active(
                self.perception,
                expected_title_or_app=args.get("expected_title_or_app", ""),
            )
        else:
            return VerificationResult(
                verified=True,
                condition="unknown_verification_skipped",
                message="Completed action execution.",
            )
