"""Browser interaction tool and Playwright automation for JARVIS Phase 3.

Maintains backward compatibility with Phase 1 BrowserTool while providing
structured Playwright automation for navigation, element interaction, inspection,
and verification.
"""

import logging
import urllib.parse
import webbrowser
from typing import Any, Dict, List, Optional

from tools.base import BaseTool, RiskLevel, ToolResult
from security.audit import audit_logger
from tools.browser.navigation import (
    sanitize_url,
    build_search_url,
    sanitize_webpage_content,
    BrowserNavigationError,
)
from tools.browser.interaction import (
    ElementTarget,
    perform_click,
    perform_fill,
    perform_press,
    perform_scroll,
    BrowserActionError,
)

logger = logging.getLogger("jarvis.tools.browser")


# ============================================================================
# PLAYWRIGHT BROWSER MANAGER (Singleton / Managed Session)
# ============================================================================

class PlaywrightBrowserManager:
    """Manages Playwright browser lifecycle, page context, and observations."""

    _instance: Optional["PlaywrightBrowserManager"] = None

    def __init__(self, default_headless: bool = False):
        self.default_headless = default_headless
        self._playwright: Optional[Any] = None
        self._browser: Optional[Any] = None
        self._context: Optional[Any] = None
        self._page: Optional[Any] = None

    @classmethod
    def get_instance(cls, default_headless: bool = False) -> "PlaywrightBrowserManager":
        if cls._instance is None:
            cls._instance = cls(default_headless=default_headless)
        return cls._instance

    @property
    def is_active(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    def get_page(self, headless: Optional[bool] = None) -> Any:
        """Ensure browser and page are open and return active Page."""
        if self._page is not None and not self._page.is_closed():
            return self._page

        from playwright.sync_api import sync_playwright

        is_headless = self.default_headless if headless is None else headless
        if self._playwright is None:
            self._playwright = sync_playwright().start()

        if self._browser is None:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
            ]
            if is_headless:
                launch_args.extend(["--no-sandbox", "--disable-gpu"])

            try:
                # Attempt to launch system Google Chrome
                self._browser = self._playwright.chromium.launch(
                    channel="chrome",
                    headless=is_headless,
                    args=launch_args,
                )
                logger.info(f"Launched system Chrome browser (headless={is_headless})")
            except Exception as exc:
                logger.info(f"System Chrome unavailable ({exc}); falling back to bundled Chromium")
                self._browser = self._playwright.chromium.launch(
                    headless=is_headless,
                    args=launch_args,
                )

        if self._context is None:
            self._context = self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            )
            try:
                self._context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
            except Exception:
                pass

        self._page = self._context.new_page()
        return self._page

    def navigate(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout_ms: int = 15000,
        headless: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Navigate active page to URL."""
        page = self.get_page(headless=headless)
        clean_url = sanitize_url(url)
        logger.info(f"Navigating to {clean_url} (wait_until={wait_until})")
        
        response = page.goto(clean_url, wait_until=wait_until, timeout=timeout_ms)
        page.wait_for_timeout(1000)  # Brief pause for dynamic hydration

        status = response.status if response else 200
        current_url = page.url
        title = page.title()

        return {
            "url": current_url,
            "title": title,
            "status": status,
        }

    def inspect_page(self, max_elements: int = 25) -> Dict[str, Any]:
        """Extract structured UI state, title, and interactive elements."""
        if not self.is_active:
            return {"active": False, "message": "Browser is not open"}

        page = self._page
        title = page.title()
        url = page.url

        # Extract structured interactive elements from DOM
        elements: List[Dict[str, Any]] = []
        try:
            # Query buttons, inputs, links, searchboxes
            raw_elements = page.query_selector_all("button, input, a, [role='button'], [role='searchbox'], textarea")
            for el in raw_elements[:max_elements]:
                try:
                    if not el.is_visible():
                        continue
                    tag_name = el.evaluate("el => el.tagName.toLowerCase()")
                    role = el.get_attribute("role") or tag_name
                    name = (
                        el.get_attribute("aria-label")
                        or el.get_attribute("name")
                        or el.get_attribute("placeholder")
                        or (el.inner_text() or "").strip()[:50]
                    )
                    el_type = el.get_attribute("type") or ""
                    elements.append({
                        "tag": tag_name,
                        "role": role,
                        "name": name,
                        "type": el_type,
                    })
                except Exception:
                    continue
        except Exception as exc:
            logger.warning(f"Error querying interactive elements: {exc}")

        # Extract visible text snippet
        body_text = ""
        contains_injection = False
        try:
            raw_body = page.inner_text("body", timeout=2000) or ""
            # Truncate and sanitize against prompt injection
            body_text, contains_injection = sanitize_webpage_content(raw_body[:1000])
        except Exception:
            pass

        return {
            "active": True,
            "url": url,
            "title": title,
            "elements_count": len(elements),
            "elements": elements,
            "content_snippet": body_text,
            "contains_injection_attempt": contains_injection,
        }

    def close(self) -> None:
        """Safely close page, context, and browser."""
        try:
            if self._page and not self._page.is_closed():
                self._page.close()
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception as exc:
            logger.warning(f"Error during browser cleanup: {exc}")
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            logger.info("Playwright browser closed.")


# ============================================================================
# PHASE 1 RETRO-COMPATIBLE BROWSER TOOL
# ============================================================================

class BrowserTool(BaseTool):
    """Safely opens URLs or performs web searches in the system default web browser."""

    name: str = "open_browser"
    description: str = (
        "Open a web page URL or search the web in the system default web browser. "
        "Supports full URLs (e.g. 'https://github.com') or search terms."
    )
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False

    ALLOWED_SCHEMES = ("http", "https")

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The web URL to open (e.g. https://python.org).",
                },
                "search_query": {
                    "type": "string",
                    "description": "Search query if searching the web instead of a specific URL.",
                },
            },
        }

    def _sanitize_url(self, target: str) -> Optional[str]:
        """Validate and format target URL."""
        try:
            return sanitize_url(target)
        except BrowserNavigationError:
            return None

    def execute(self, **kwargs: Any) -> ToolResult:
        url: Optional[str] = kwargs.get("url")
        search_query: Optional[str] = kwargs.get("search_query")

        target_url = None
        action_desc = ""

        if url:
            target_url = self._sanitize_url(url)
            if not target_url:
                return ToolResult(
                    success=False,
                    error=f"Invalid or disallowed URL scheme: '{url}'. Only HTTP/HTTPS URLs are allowed.",
                )
            action_desc = f"Opening {target_url}"
        elif search_query:
            target_url = build_search_url(search_query)
            action_desc = f"Searching for '{search_query}'"
        else:
            return ToolResult(
                success=False,
                error="Either 'url' or 'search_query' must be provided.",
            )

        try:
            opened = webbrowser.open(target_url)
            audit_logger.log_event("BROWSER_OPENED", {"url": target_url, "success": opened})
            return ToolResult(
                success=True,
                output={
                    "message": f"Browser successfully launched: {action_desc}.",
                    "target_url": target_url,
                },
            )
        except Exception as exc:
            logger.error(f"Failed to open browser URL '{target_url}': {exc}")
            return ToolResult(
                success=False,
                error=f"Failed to launch browser: {str(exc)}",
            )


# ============================================================================
# PHASE 3 TOOLS: PLAYWRIGHT BROWSER AUTOMATION TOOLS
# ============================================================================

class BrowserNavigateTool(BaseTool):
    """Navigates the browser to a URL or searches the web via Playwright."""

    name: str = "browser_navigate"
    description: str = (
        "Navigate to a URL or web search query using an automated browser session. "
        "Allows subsequent observation and interaction with page elements."
    )
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False

    def __init__(self, manager: Optional[PlaywrightBrowserManager] = None):
        self.manager = manager or PlaywrightBrowserManager.get_instance()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Destination URL (e.g. 'https://github.com').",
                },
                "search_query": {
                    "type": "string",
                    "description": "Optional search query to navigate directly to Google search.",
                },
                "headless": {
                    "type": "boolean",
                    "description": "Run in headless mode (default: false for visual automation).",
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        url: Optional[str] = kwargs.get("url")
        search_query: Optional[str] = kwargs.get("search_query")
        headless: Optional[bool] = kwargs.get("headless")

        if search_query:
            target_url = build_search_url(search_query)
        elif url:
            target_url = url
        else:
            return ToolResult(
                success=False,
                error="Either 'url' or 'search_query' must be provided.",
            )

        try:
            result = self.manager.navigate(target_url, headless=headless)
            audit_logger.log_event("BROWSER_NAVIGATED", {
                "url": result["url"],
                "title": result["title"],
                "status": result["status"],
            })
            return ToolResult(
                success=True,
                output={
                    "message": f"Successfully navigated to {result['url']}.",
                    "url": result["url"],
                    "title": result["title"],
                    "status": result["status"],
                },
            )
        except Exception as exc:
            logger.error(f"Browser navigation failed: {exc}")
            return ToolResult(
                success=False,
                error=f"Navigation failed: {str(exc)}",
            )


class BrowserInteractTool(BaseTool):
    """Executes a structured action (click, fill, press, scroll) on the webpage."""

    name: str = "browser_interact"
    description: str = (
        "Perform a structured action on the active webpage, such as clicking a button, "
        "typing text into a field, pressing keyboard keys, or scrolling."
    )
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False

    def __init__(self, manager: Optional[PlaywrightBrowserManager] = None):
        self.manager = manager or PlaywrightBrowserManager.get_instance()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["click", "fill", "press", "scroll"],
                    "description": "The interaction action to perform.",
                },
                "target": {
                    "type": "object",
                    "description": "Target element selector (e.g. {'role': 'button', 'name': 'Search'} or {'selector': 'textarea[name=\"q\"]'}).",
                    "properties": {
                        "role": {"type": "string"},
                        "name": {"type": "string"},
                        "text": {"type": "string"},
                        "selector": {"type": "string"},
                        "placeholder": {"type": "string"},
                        "label": {"type": "string"},
                    },
                },
                "value": {
                    "type": "string",
                    "description": "Text value to fill into an input or key to press.",
                },
                "press_enter": {
                    "type": "boolean",
                    "description": "Whether to press Enter immediately after filling (default: false).",
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Scroll direction (default: down).",
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        if not self.manager.is_active:
            return ToolResult(
                success=False,
                error="No active browser session. Call browser_navigate first.",
            )

        page = self.manager._page
        action = kwargs.get("action", "").lower()
        target_dict = kwargs.get("target") or {}
        value = kwargs.get("value", "")
        press_enter = kwargs.get("press_enter", False)
        direction = kwargs.get("direction", "down")

        target = ElementTarget(**target_dict) if target_dict else ElementTarget()

        try:
            if action == "click":
                res = perform_click(page, target)
            elif action == "fill":
                if not value:
                    return ToolResult(success=False, error="Action 'fill' requires a non-empty 'value'.")
                res = perform_fill(page, target, value, press_enter=press_enter)
            elif action == "press":
                key = value or kwargs.get("key", "Enter")
                res = perform_press(page, key, target if target.has_criteria() else None)
            elif action == "scroll":
                res = perform_scroll(page, direction=direction)
            else:
                return ToolResult(success=False, error=f"Unsupported browser action '{action}'.")

            audit_logger.log_event("BROWSER_INTERACTION", res)
            return ToolResult(success=True, output=res)
        except Exception as exc:
            logger.error(f"Browser interaction '{action}' failed: {exc}")
            return ToolResult(
                success=False,
                error=f"Interaction '{action}' failed: {str(exc)}",
            )


class BrowserInspectTool(BaseTool):
    """Observes the current webpage state and extracts structured UI elements."""

    name: str = "browser_inspect"
    description: str = (
        "Observe the current webpage state, returning the current URL, page title, "
        "and accessible interactive elements for planning the next action."
    )
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False

    def __init__(self, manager: Optional[PlaywrightBrowserManager] = None):
        self.manager = manager or PlaywrightBrowserManager.get_instance()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_elements": {
                    "type": "integer",
                    "description": "Maximum number of interactive elements to return (default: 25).",
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        max_elements = kwargs.get("max_elements", 25)
        state = self.manager.inspect_page(max_elements=max_elements)
        audit_logger.log_event("BROWSER_INSPECT", {
            "url": state.get("url"),
            "title": state.get("title"),
            "elements_count": state.get("elements_count", 0),
        })
        return ToolResult(success=True, output=state)


class BrowserCloseTool(BaseTool):
    """Closes the automated browser session."""

    name: str = "browser_close"
    description: str = "Close the current active automated browser session."
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False

    def __init__(self, manager: Optional[PlaywrightBrowserManager] = None):
        self.manager = manager or PlaywrightBrowserManager.get_instance()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    def execute(self, **kwargs: Any) -> ToolResult:
        self.manager.close()
        audit_logger.log_event("BROWSER_CLOSED", {})
        return ToolResult(
            success=True,
            output={"message": "Automated browser closed successfully."},
        )
