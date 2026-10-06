"""Browser interaction tool for JARVIS.

Allows opening URLs and performing safe web searches using the system's
default web browser.
"""

import logging
import urllib.parse
import webbrowser
from typing import Any, Dict, Optional

from tools.base import BaseTool, RiskLevel, ToolResult
from security.audit import audit_logger

logger = logging.getLogger("jarvis.tools.browser")


class BrowserTool(BaseTool):
    """Safely opens URLs or performs web searches in the default browser."""

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
        cleaned = target.strip()
        if not cleaned:
            return None

        parsed = urllib.parse.urlparse(cleaned)
        if not parsed.scheme:
            # If no scheme provided (e.g. 'google.com'), default to https://
            cleaned = f"https://{cleaned}"
            parsed = urllib.parse.urlparse(cleaned)

        if parsed.scheme.lower() not in self.ALLOWED_SCHEMES:
            logger.warning(f"Blocked invalid URL scheme: {parsed.scheme}")
            return None

        return cleaned

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
            query_encoded = urllib.parse.quote_plus(search_query.strip())
            target_url = f"https://www.google.com/search?q={query_encoded}"
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
