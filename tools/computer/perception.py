"""Computer perception for JARVIS Phase 3.

Provides structured screen and window state observation, UI accessibility tree inspection,
and ephemeral on-demand screenshots without continuous surveillance.
"""

import ctypes
from ctypes import wintypes
import logging
import os
import tempfile
import time
from typing import Any, Dict, List, Optional
import psutil

from tools.base import BaseTool, RiskLevel, ToolResult
from security.audit import audit_logger

logger = logging.getLogger("jarvis.tools.computer.perception")


class ComputerPerception:
    """Observes active desktop applications, window hierarchy, and accessible UI elements."""

    def __init__(self):
        self._temp_screenshots: List[str] = []

    def get_active_window(self) -> Dict[str, Any]:
        """Detect the currently focused window, its application name, and PID."""
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return {
                "hwnd": 0,
                "title": "",
                "application": "",
                "pid": 0,
            }

        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf_size = max(length + 1, 512)
        buff = ctypes.create_unicode_buffer(buf_size)
        ctypes.windll.user32.GetWindowTextW(hwnd, buff, buf_size)
        title = buff.value

        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        app_name = ""
        if pid.value:
            try:
                proc = psutil.Process(pid.value)
                app_name = proc.name()
            except Exception:
                pass

        return {
            "hwnd": hwnd,
            "title": title,
            "application": app_name,
            "pid": pid.value,
        }

    def inspect_ui_tree(self, max_elements: int = 25) -> List[Dict[str, Any]]:
        """Inspect accessible UI elements of the foreground window via UI Automation."""
        elements: List[Dict[str, Any]] = []
        try:
            from pywinauto import Desktop

            active_info = self.get_active_window()
            hwnd = active_info.get("hwnd")
            if not hwnd:
                return elements

            app_win = Desktop(backend="uia").window(handle=hwnd)
            children = app_win.children()

            for child in children[:max_elements]:
                try:
                    name = child.window_text() or ""
                    elem_type = child.element_info.control_type or ""
                    is_enabled = child.is_enabled()
                    is_visible = child.is_visible()
                    if is_visible:
                        elements.append({
                            "name": name.strip(),
                            "control_type": elem_type,
                            "enabled": is_enabled,
                            "visible": is_visible,
                        })
                except Exception:
                    continue
        except Exception as exc:
            logger.debug(f"UI tree inspection via pywinauto skipped or limited: {exc}")

        return elements

    def capture_screenshot(self, ephemeral: bool = True) -> Optional[str]:
        """Capture an on-demand screenshot.
        
        If ephemeral is True, the screenshot is recorded for cleanup and not permanently retained.
        """
        try:
            from PIL import ImageGrab

            img = ImageGrab.grab()
            fd, path = tempfile.mkstemp(prefix="jarvis_snap_", suffix=".png")
            os.close(fd)
            img.save(path)

            if ephemeral:
                self._temp_screenshots.append(path)

            logger.info(f"Captured screen state: {path} (ephemeral={ephemeral})")
            return path
        except Exception as exc:
            logger.error(f"Failed to capture screenshot: {exc}")
            return None

    def cleanup_ephemeral_screenshots(self) -> None:
        """Remove any temporary screenshots captured during execution."""
        for path in self._temp_screenshots:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        self._temp_screenshots.clear()

    def perform_ocr(self, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Perform on-demand local Windows OCR on a screenshot or provided image file."""
        from PIL import Image
        temp_path = None
        try:
            if image_path and os.path.exists(image_path):
                img = Image.open(image_path)
            else:
                temp_path = self.capture_screenshot(ephemeral=True)
                if not temp_path or not os.path.exists(temp_path):
                    return {"text": "", "lines": [], "available": False, "error": "Could not capture screen"}
                img = Image.open(temp_path)

            try:
                import winocr
                ocr_data = winocr.recognize_pil_sync(img)
                lines = [l.get("text", "") for l in ocr_data.get("lines", [])]
                full_text = ocr_data.get("text", "").strip()
                return {
                    "text": full_text,
                    "lines": lines,
                    "lines_count": len(lines),
                    "available": True,
                }
            except ImportError:
                logger.debug("winocr is not installed; OCR fallback unavailable.")
                return {"text": "", "lines": [], "available": False, "error": "winocr not installed"}
            except Exception as exc:
                logger.warning(f"Windows OCR recognition failed: {exc}")
                return {"text": "", "lines": [], "available": False, "error": str(exc)}
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def observe(self, include_elements: bool = True, include_ocr: bool = False) -> Dict[str, Any]:
        """Produce a comprehensive structured observation of the computer state."""
        window_info = self.get_active_window()
        elements = self.inspect_ui_tree() if include_elements else []

        observation: Dict[str, Any] = {
            "timestamp": time.time(),
            "active_window": window_info.get("title", ""),
            "application": window_info.get("application", ""),
            "pid": window_info.get("pid", 0),
            "elements_count": len(elements),
            "elements": elements,
        }

        # If requested or if UI elements tree is empty (legacy or non-UIA app), provide OCR text
        if include_ocr or (include_elements and len(elements) == 0):
            ocr_res = self.perform_ocr()
            if ocr_res.get("available") and ocr_res.get("text"):
                observation["ocr_text"] = ocr_res["text"]
                observation["ocr_lines"] = ocr_res["lines"][:10]

        audit_logger.log_event("COMPUTER_PERCEPTION", {
            "application": observation["application"],
            "window": observation["active_window"],
            "elements_count": observation["elements_count"],
        })
        return observation


class ComputerPerceptionTool(BaseTool):
    """Tool for observing the current Windows desktop application state and UI elements."""

    name: str = "observe_screen"
    description: str = (
        "Observe the current active Windows application, window title, and accessible UI elements. "
        "Provides structured computer perception and local OCR fallback without raw coordinates."
    )
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False

    def __init__(self, perception: Optional[ComputerPerception] = None):
        self.perception = perception or ComputerPerception()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "include_elements": {
                    "type": "boolean",
                    "description": "Whether to inspect accessible UI elements in the active window (default: true).",
                },
                "include_ocr": {
                    "type": "boolean",
                    "description": "Whether to extract visible text via local Windows OCR (default: false).",
                },
            },
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        include_elements = kwargs.get("include_elements", True)
        include_ocr = kwargs.get("include_ocr", False)
        observation = self.perception.observe(include_elements=include_elements, include_ocr=include_ocr)
        return ToolResult(
            success=True,
            output=observation,
        )
