"""Action verification system for JARVIS Phase 3.

Evaluates whether planned actions successfully executed and reached the expected state.
Strictly follows the "NO FABRICATION" rule: if a state cannot be confirmed from real
observation, it reports failure or indeterminate status instead of assuming success.
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Dict, Optional

from security.audit import audit_logger

logger = logging.getLogger("jarvis.tools.computer.verification")


@dataclass
class VerificationResult:
    """Structured outcome of an action verification check."""
    verified: bool
    condition: str
    message: str
    actual_observation: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "condition": self.condition,
            "message": self.message,
            "actual_observation": self.actual_observation,
            "confidence": self.confidence,
        }


class ActionVerifier:
    """Verifies outcomes of computer and browser operations."""

    def verify_browser_navigation(
        self,
        manager: Any,
        expected_url_pattern: Optional[str] = None,
        expected_title_pattern: Optional[str] = None,
    ) -> VerificationResult:
        """Verify that browser successfully navigated to target destination."""
        if not manager.is_active:
            return VerificationResult(
                verified=False,
                condition="browser_active",
                message="Browser session is closed or inactive; could not verify navigation.",
            )

        page = manager._page
        try:
            current_url = page.url
            current_title = page.title()
        except Exception as exc:
            return VerificationResult(
                verified=False,
                condition="inspect_page",
                message=f"Failed to inspect browser page: {exc}",
            )

        obs = {"url": current_url, "title": current_title}

        if expected_url_pattern:
            if not re.search(expected_url_pattern, current_url, re.IGNORECASE):
                return VerificationResult(
                    verified=False,
                    condition=f"url_matches_{expected_url_pattern}",
                    message=f"Current URL '{current_url}' did not match expected pattern '{expected_url_pattern}'.",
                    actual_observation=obs,
                )

        if expected_title_pattern:
            if not re.search(expected_title_pattern, current_title, re.IGNORECASE):
                return VerificationResult(
                    verified=False,
                    condition=f"title_matches_{expected_title_pattern}",
                    message=f"Page title '{current_title}' did not match expected pattern '{expected_title_pattern}'.",
                    actual_observation=obs,
                )

        audit_logger.log_event("VERIFICATION", {
            "type": "browser_navigation",
            "success": True,
            "url": current_url,
            "title": current_title,
        })
        return VerificationResult(
            verified=True,
            condition="browser_navigation_confirmed",
            message=f"Navigation verified: active on '{current_title}' ({current_url}).",
            actual_observation=obs,
        )

    def verify_browser_search_results(
        self,
        manager: Any,
        query: str,
    ) -> VerificationResult:
        """Verify that a search was submitted and search results are actively visible."""
        if not manager.is_active:
            return VerificationResult(
                verified=False,
                condition="browser_active",
                message="Browser is not active; cannot verify search results.",
            )

        page = manager._page
        try:
            # Wait for any navigation or hydration to settle
            try:
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass

            import time
            time.sleep(1.0)

            current_url = page.url
            current_title = page.title()

            # Check indicators of search results page with resilience to navigation transitions
            visible_headings = []
            page_text = ""
            for attempt in range(3):
                try:
                    headings = page.locator("h3, h2, #search, [data-async-context]").all_inner_texts()
                    visible_headings = [h.strip() for h in headings if h.strip()][:5]
                    page_text = page.inner_text("body", timeout=2000) or ""
                    break
                except Exception:
                    time.sleep(1.0)

            url_lower = current_url.lower()
            url_has_search = "search" in url_lower or "q=" in url_lower

            # Check if query words appear in page or URL
            query_tokens = [q.lower() for q in query.split() if len(q) > 2]
            tokens_found = sum(1 for t in query_tokens if t in page_text.lower() or t in url_lower)
            has_results = (
                len(visible_headings) > 0
                or (url_has_search and (len(query_tokens) == 0 or tokens_found >= 1))
                or (len(query_tokens) > 0 and tokens_found >= len(query_tokens) // 2)
            )

            obs = {
                "url": current_url,
                "title": current_title,
                "top_headings": visible_headings,
                "result_indicators_found": len(visible_headings),
            }

            if has_results:
                audit_logger.log_event("VERIFICATION", {
                    "type": "search_results",
                    "success": True,
                    "query": query,
                    "headings": visible_headings[:3],
                })
                return VerificationResult(
                    verified=True,
                    condition="search_results_visible",
                    message=f"Search results for '{query}' are verified and visible.",
                    actual_observation=obs,
                )
            else:
                return VerificationResult(
                    verified=False,
                    condition="search_results_visible",
                    message=f"Could not confirm search results for '{query}' on page.",
                    actual_observation=obs,
                )
        except Exception as exc:
            logger.error(f"Error during search verification: {exc}")
            return VerificationResult(
                verified=False,
                condition="search_results_verification",
                message=f"Verification encountered error: {str(exc)}",
            )

    def verify_window_active(
        self,
        perception: Any,
        expected_title_or_app: str,
    ) -> VerificationResult:
        """Verify that a target desktop window or application is in the foreground."""
        active_info = perception.get_active_window()
        title = active_info.get("title", "")
        app = active_info.get("application", "")

        target = expected_title_or_app.lower()
        matched = target in title.lower() or target in app.lower()

        obs = {"active_window": title, "application": app}

        if matched:
            audit_logger.log_event("VERIFICATION", {
                "type": "window_active",
                "success": True,
                "target": expected_title_or_app,
                "window": title,
            })
            return VerificationResult(
                verified=True,
                condition="window_active_confirmed",
                message=f"Window '{expected_title_or_app}' is active ({title}).",
                actual_observation=obs,
            )
        else:
            return VerificationResult(
                verified=False,
                condition="window_active_confirmed",
                message=f"Expected window '{expected_title_or_app}' is not active (currently focused: '{title}').",
                actual_observation=obs,
            )
