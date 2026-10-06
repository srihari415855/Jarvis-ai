"""Controlled Windows GUI interaction for JARVIS Phase 3.

Provides structured window focus, UI element interaction, keyboard actions,
and hotkeys through Windows UI Automation with strict parameter validation.
Raw arbitrary coordinate clicking by the LLM is prohibited.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from tools.base import BaseTool, RiskLevel, ToolResult
from security.audit import audit_logger

logger = logging.getLogger("jarvis.tools.computer.control")

FORBIDDEN_HOTKEYS = [
    ["alt", "f4"],  # window termination
    ["ctrl", "alt", "del"],
    ["win", "l"],  # lock
]


class UIControlTarget(BaseModel):
    """Target element in a Windows GUI application."""
    name: Optional[str] = Field(default=None, description="Accessible name or title of the element, e.g. 'Search'")
    control_type: Optional[str] = Field(default=None, description="UI control type, e.g. 'Button', 'Edit', 'MenuItem'")
    window_title: Optional[str] = Field(default=None, description="Window title containing the element")


class ComputerControl:
    """Manages controlled Windows desktop interactions via UI Automation."""

    def focus_window(self, title_or_app: str) -> Dict[str, Any]:
        """Focus a desktop window by title or executable name."""
        from pywinauto import Desktop
        cleaned = title_or_app.strip()
        if not cleaned:
            raise ValueError("Target window title or app must not be empty.")

        desktop = Desktop(backend="uia")
        # Try matching active windows
        candidates = desktop.windows()
        target_win = None
        for win in candidates:
            try:
                t = win.window_text()
                if cleaned.lower() in t.lower():
                    target_win = win
                    break
            except Exception:
                continue

        if not target_win:
            raise RuntimeError(f"Window matching '{cleaned}' was not found.")

        target_win.set_focus()
        time.sleep(0.3)
        return {
            "action": "focus_window",
            "target": cleaned,
            "focused_title": target_win.window_text(),
            "status": "focused",
        }

    def click_element(self, target: UIControlTarget) -> Dict[str, Any]:
        """Find an accessible UI element and click it."""
        from pywinauto import Desktop

        if not target.name and not target.control_type:
            raise ValueError("Target must specify 'name' or 'control_type'.")

        desktop = Desktop(backend="uia")
        # Look within target window or top foreground window
        if target.window_title:
            win = desktop.window(title_re=f".*{target.window_title}.*")
        else:
            win = desktop.top_window()

        kwargs: Dict[str, Any] = {}
        if target.name:
            kwargs["title"] = target.name
        if target.control_type:
            kwargs["control_type"] = target.control_type

        elem = win.child_window(**kwargs)
        if not elem.exists(timeout=3):
            raise RuntimeError(f"UI Element not found: {target.model_dump(exclude_none=True)}")

        elem.click_input()
        logger.info(f"Clicked Windows UI element: {target.model_dump(exclude_none=True)}")
        return {
            "action": "click_element",
            "target": target.model_dump(exclude_none=True),
            "status": "clicked",
        }

    def type_text(self, text: str, target: Optional[UIControlTarget] = None) -> Dict[str, Any]:
        """Type text into focused element or specified target."""
        from pywinauto.keyboard import send_keys

        if target and (target.name or target.control_type):
            self.click_element(target)

        # Sanitize text for pywinauto send_keys
        # Escape special pywinauto characters: { } + ^ % ~
        escaped = (
            text.replace("{", "{{")
            .replace("}", "}}")
            .replace("+", "{+}")
            .replace("^", "{^}")
            .replace("%", "{%}")
            .replace("~", "{~}")
        )
        send_keys(escaped, with_spaces=True)
        logger.info(f"Typed text ({len(text)} chars)")
        return {
            "action": "type_text",
            "chars_typed": len(text),
            "status": "typed",
        }

    def press_key(self, key: str) -> Dict[str, Any]:
        """Press a keyboard key."""
        from pywinauto.keyboard import send_keys

        key_clean = key.strip().lower()
        key_mapping = {
            "enter": "{ENTER}",
            "tab": "{TAB}",
            "esc": "{ESC}",
            "escape": "{ESC}",
            "backspace": "{BACKSPACE}",
            "space": "{SPACE}",
            "down": "{DOWN}",
            "up": "{UP}",
            "left": "{LEFT}",
            "right": "{RIGHT}",
        }
        send_key_str = key_mapping.get(key_clean, f"{{{key_clean.upper()}}}")
        send_keys(send_key_str)
        logger.info(f"Pressed key: {key}")
        return {
            "action": "press_key",
            "key": key,
            "status": "pressed",
        }

    def hotkey(self, keys: List[str]) -> Dict[str, Any]:
        """Execute a key combination."""
        from pywinauto.keyboard import send_keys

        clean_keys = [k.strip().lower() for k in keys]
        for forbidden in FORBIDDEN_HOTKEYS:
            if set(forbidden).issubset(set(clean_keys)):
                raise ValueError(f"Hotkey combination '{keys}' is forbidden by security policy.")

        # Build pywinauto hotkey string
        # e.g. ctrl+c -> ^c, alt+tab -> %{TAB}
        prefix = ""
        main_key = ""
        for k in clean_keys:
            if k == "ctrl":
                prefix += "^"
            elif k == "alt":
                prefix += "%"
            elif k == "shift":
                prefix += "+"
            else:
                main_key = k

        if main_key:
            send_keys(f"{prefix}{{{main_key.upper()}}}")
        return {
            "action": "hotkey",
            "keys": keys,
            "status": "executed",
        }


class ComputerControlTool(BaseTool):
    """Tool for safe, validated Windows desktop GUI control."""

    name: str = "computer_control"
    description: str = (
        "Control Windows applications safely by focusing windows, clicking buttons/inputs "
        "by accessible name, typing text, or pressing keys. Does not accept arbitrary coordinates."
    )
    risk_level: RiskLevel = RiskLevel.MEDIUM
    requires_confirmation: bool = False

    def __init__(self, control: Optional[ComputerControl] = None):
        self.control = control or ComputerControl()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["focus_window", "click", "type", "press", "hotkey"],
                    "description": "Desktop GUI action to perform.",
                },
                "window_title": {
                    "type": "string",
                    "description": "Window title to focus or target.",
                },
                "target": {
                    "type": "object",
                    "description": "Target UI element (name, control_type).",
                    "properties": {
                        "name": {"type": "string"},
                        "control_type": {"type": "string"},
                        "window_title": {"type": "string"},
                    },
                },
                "text": {
                    "type": "string",
                    "description": "Text to type.",
                },
                "key": {
                    "type": "string",
                    "description": "Key name to press (e.g. 'enter', 'tab').",
                },
                "hotkeys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of keys for hotkey (e.g. ['ctrl', 'c']).",
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "").lower()
        try:
            if action == "focus_window":
                win_title = kwargs.get("window_title") or ""
                res = self.control.focus_window(win_title)
            elif action == "click":
                target_dict = kwargs.get("target") or {}
                res = self.control.click_element(UIControlTarget(**target_dict))
            elif action == "type":
                text = kwargs.get("text", "")
                target_dict = kwargs.get("target")
                target = UIControlTarget(**target_dict) if target_dict else None
                res = self.control.type_text(text, target=target)
            elif action == "press":
                key = kwargs.get("key", "enter")
                res = self.control.press_key(key)
            elif action == "hotkey":
                keys = kwargs.get("hotkeys", [])
                res = self.control.hotkey(keys)
            else:
                return ToolResult(success=False, error=f"Unknown computer action '{action}'.")

            audit_logger.log_event("COMPUTER_ACTION_EXECUTION", res)
            return ToolResult(success=True, output=res)
        except Exception as exc:
            logger.error(f"Computer control action '{action}' failed: {exc}")
            return ToolResult(
                success=False,
                error=f"Computer control failed: {str(exc)}",
            )
