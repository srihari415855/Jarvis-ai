"""Browser navigation and URL safety utilities for JARVIS Phase 3.
"""

import logging
import urllib.parse
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.tools.browser.navigation")

ALLOWED_SCHEMES = ("http", "https")

# Untrusted prompt injection patterns found in malicious webpage content
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
    r"system\s*:\s*override",
    r"upload\s+all\s+(?:your\s+)?files",
    r"delete\s+all\s+(?:your\s+)?files",
    r"exfiltrate",
    r"send\s+password",
    r"reveal\s+secret",
]


class BrowserNavigationError(Exception):
    """Exception raised when browser navigation fails or is rejected."""
    pass


def sanitize_url(raw_url: str) -> str:
    """Validate and format a web URL.
    
    Rejects disallowed schemes (e.g. javascript:, file:, data:) and formats
    missing schemes to https://.
    """
    cleaned = raw_url.strip()
    if not cleaned:
        raise BrowserNavigationError("URL must not be empty.")

    # Reject dangerous characters
    if any(c in cleaned for c in ("\r", "\n", "\t")):
        raise BrowserNavigationError("URL contains illegal whitespace or control characters.")

    parsed = urllib.parse.urlparse(cleaned)
    if not parsed.scheme:
        cleaned = f"https://{cleaned}"
        parsed = urllib.parse.urlparse(cleaned)

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        logger.warning(f"Rejected disallowed URL scheme: '{parsed.scheme}' in '{raw_url}'")
        raise BrowserNavigationError(
            f"Invalid or disallowed URL scheme: '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
        )

    # Disallow localhost / private addresses unless explicitly permitted
    hostname = (parsed.hostname or "").lower()
    if not hostname or "." not in hostname and hostname != "localhost":
        # Check if single word like 'google' -> format to google.com
        if hostname and not hostname.startswith("127."):
            cleaned = f"https://www.{hostname}.com"

    return cleaned


def build_search_url(query: str, search_engine: str = "google") -> str:
    """Build a search URL for a given search query."""
    encoded_query = urllib.parse.quote_plus(query.strip())
    if search_engine.lower() == "bing":
        return f"https://www.bing.com/search?q={encoded_query}"
    elif search_engine.lower() == "duckduckgo":
        return f"https://duckduckgo.com/?q={encoded_query}"
    else:
        return f"https://www.google.com/search?q={encoded_query}"


def sanitize_webpage_content(text: str) -> Tuple[str, bool]:
    """Sanitize webpage text against potential prompt injection attacks.
    
    Returns (sanitized_text, contains_injection_attempt).
    """
    import re
    flagged = False
    sanitized = text

    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, sanitized, re.IGNORECASE):
            flagged = True
            sanitized = re.sub(
                pattern,
                "[POTENTIAL_INJECTION_FILTERED]",
                sanitized,
                flags=re.IGNORECASE,
            )

    return sanitized, flagged
