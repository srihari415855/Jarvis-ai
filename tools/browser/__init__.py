"""Browser tools and automation package for JARVIS.
"""

from tools.browser.browser import (
    BrowserTool,
    BrowserNavigateTool,
    BrowserInteractTool,
    BrowserInspectTool,
    BrowserCloseTool,
    PlaywrightBrowserManager,
)
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

__all__ = [
    "BrowserTool",
    "BrowserNavigateTool",
    "BrowserInteractTool",
    "BrowserInspectTool",
    "BrowserCloseTool",
    "PlaywrightBrowserManager",
    "sanitize_url",
    "build_search_url",
    "sanitize_webpage_content",
    "BrowserNavigationError",
    "ElementTarget",
    "perform_click",
    "perform_fill",
    "perform_press",
    "perform_scroll",
    "BrowserActionError",
]
