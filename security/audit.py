"""Structured security audit logger and privacy-preserving sanitizer.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from config.settings import settings

# Sensitive keyword patterns to sanitize before logging
SENSITIVE_PATTERNS = [
    re.compile(r"(api[_-]?key\s*[:=]\s*)['\"]?([^'\"\s]+)['\"]?", re.IGNORECASE),
    re.compile(r"(password\s*[:=]\s*)['\"]?([^'\"\s]+)['\"]?", re.IGNORECASE),
    re.compile(r"(token\s*[:=]\s*)['\"]?([^'\"\s]+)['\"]?", re.IGNORECASE),
    re.compile(r"(secret\s*[:=]\s*)['\"]?([^'\"\s]+)['\"]?", re.IGNORECASE),
    re.compile(r"(private[_-]?key\s*[:=]\s*)['\"]?([^'\"\s]+)['\"]?", re.IGNORECASE),
]


def sanitize_sensitive_data(text: str) -> str:
    """Mask credentials, tokens, and passwords from logs."""
    sanitized = text
    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(r"\1[REDACTED]", sanitized)
    return sanitized


class AuditLogger:
    """Maintains an append-only, in-memory and persistent security audit log."""

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or settings.LOGS_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.log_dir / "audit.jsonl"
        self._memory_log: List[Dict[str, Any]] = []
        self._logger = logging.getLogger("jarvis.audit")

    def log_event(
        self,
        event_type: str,
        details: Dict[str, Any],
        level: int = logging.INFO,
    ) -> Dict[str, Any]:
        """Record an auditable security event."""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Sanitize string values inside details
        sanitized_details = {}
        for k, v in details.items():
            if isinstance(v, str):
                sanitized_details[k] = sanitize_sensitive_data(v)
            else:
                sanitized_details[k] = v

        entry = {
            "timestamp": timestamp,
            "event_type": event_type,
            "details": sanitized_details,
        }

        self._memory_log.append(entry)

        # Write to audit file
        try:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as exc:
            self._logger.error(f"Failed to write to audit log: {exc}")

        # Console log
        self._logger.log(level, f"AUDIT: [{event_type}] {sanitized_details}")
        return entry

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent audit events from memory."""
        return self._memory_log[-limit:]


# Global audit logger instance
audit_logger = AuditLogger()
