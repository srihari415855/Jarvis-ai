"""Windows application management and launching tools for JARVIS.

Supports launching any installed Windows application by name, executable,
App Path, or Start Menu shortcut.
"""

import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
import psutil

try:
    import winreg
except ImportError:
    winreg = None

from config.settings import settings
from tools.base import BaseTool, RiskLevel, ToolResult
from security.audit import audit_logger

logger = logging.getLogger("jarvis.tools.applications")


def _get_antigravity_path() -> Optional[str]:
    """Locate Antigravity IDE executable safely if present."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "Programs" / "Antigravity IDE" / "Antigravity IDE.exe"
        if candidate.is_file():
            return str(candidate)
    return None


# Well-known application aliases and system executables
KNOWN_SYSTEM_APPS: Dict[str, Dict[str, Any]] = {
    "notepad": {
        "display_name": "Notepad",
        "executable": "notepad.exe",
        "description": "Standard Windows text editor",
    },
    "calculator": {
        "display_name": "Calculator",
        "executable": "calc.exe",
        "description": "Windows Calculator",
    },
    "calc": {
        "display_name": "Calculator",
        "executable": "calc.exe",
        "description": "Windows Calculator",
    },
    "explorer": {
        "display_name": "File Explorer",
        "executable": "explorer.exe",
        "description": "Windows File Explorer",
    },
    "file explorer": {
        "display_name": "File Explorer",
        "executable": "explorer.exe",
        "description": "Windows File Explorer",
    },
    "paint": {
        "display_name": "Paint",
        "executable": "mspaint.exe",
        "description": "Windows Paint",
    },
    "mspaint": {
        "display_name": "Paint",
        "executable": "mspaint.exe",
        "description": "Windows Paint",
    },
    "task manager": {
        "display_name": "Task Manager",
        "executable": "taskmgr.exe",
        "description": "Windows Task Manager",
    },
    "taskmgr": {
        "display_name": "Task Manager",
        "executable": "taskmgr.exe",
        "description": "Windows Task Manager",
    },
    "chrome": {
        "display_name": "Google Chrome",
        "executable": "chrome.exe",
        "description": "Google Chrome Web Browser",
    },
    "google chrome": {
        "display_name": "Google Chrome",
        "executable": "chrome.exe",
        "description": "Google Chrome Web Browser",
    },
    "edge": {
        "display_name": "Microsoft Edge",
        "executable": "msedge.exe",
        "description": "Microsoft Edge Web Browser",
    },
    "msedge": {
        "display_name": "Microsoft Edge",
        "executable": "msedge.exe",
        "description": "Microsoft Edge Web Browser",
    },
    "microsoft edge": {
        "display_name": "Microsoft Edge",
        "executable": "msedge.exe",
        "description": "Microsoft Edge Web Browser",
    },
    "brave": {
        "display_name": "Brave Browser",
        "executable": "brave.exe",
        "description": "Brave Web Browser",
    },
    "word": {
        "display_name": "Microsoft Word",
        "executable": "winword.exe",
        "description": "Microsoft Word",
    },
    "excel": {
        "display_name": "Microsoft Excel",
        "executable": "excel.exe",
        "description": "Microsoft Excel",
    },
    "powerpoint": {
        "display_name": "Microsoft PowerPoint",
        "executable": "powerpnt.exe",
        "description": "Microsoft PowerPoint",
    },
    "antigravity": {
        "display_name": "Antigravity IDE",
        "executable": _get_antigravity_path() or "Antigravity IDE.exe",
        "description": "Antigravity AI Agent IDE",
    },
    "antigravity ide": {
        "display_name": "Antigravity IDE",
        "executable": _get_antigravity_path() or "Antigravity IDE.exe",
        "description": "Antigravity AI Agent IDE",
    },
    "settings": {
        "display_name": "Windows Settings",
        "executable": "ms-settings:",
        "description": "Windows Settings App",
    },
}


class GetSystemInfoTool(BaseTool):
    """Tool to query non-sensitive host system information."""

    name = "get_system_info"
    description = "Returns host OS, CPU, RAM, Python version, and JARVIS version without exposing credentials."
    risk_level = RiskLevel.LOW
    requires_confirmation = False

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        try:
            mem = psutil.virtual_memory()
            info = {
                "jarvis_name": settings.JARVIS_NAME,
                "jarvis_version": settings.JARVIS_VERSION,
                "os": f"{platform.system()} {platform.release()} ({platform.version()})",
                "cpu": platform.processor() or platform.machine(),
                "cpu_count": psutil.cpu_count(logical=True),
                "ram_total_gb": round(mem.total / (1024 ** 3), 2),
                "ram_available_gb": round(mem.available / (1024 ** 3), 2),
                "ram_percent_used": mem.percent,
                "python_version": platform.python_version(),
            }
            audit_logger.log_event("TOOL_EXECUTION", {
                "tool_name": self.name,
                "status": "success",
            })
            return ToolResult(success=True, output=info)
        except Exception as exc:
            err = f"Failed to retrieve system info: {str(exc)}"
            logger.error(err)
            return ToolResult(success=False, error=err)


class ListAllowedApplicationsTool(BaseTool):
    """Tool to query installed or common applications."""

    name = "list_allowed_applications"
    description = "Returns common desktop applications and notes that any installed system application can be opened."
    risk_level = RiskLevel.LOW
    requires_confirmation = False

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        # Deduplicate display names
        seen = set()
        apps = []
        for app_id, data in KNOWN_SYSTEM_APPS.items():
            name = data["display_name"]
            if name not in seen:
                seen.add(name)
                apps.append({
                    "id": app_id,
                    "name": name,
                    "description": data["description"],
                })

        audit_logger.log_event("TOOL_EXECUTION", {
            "tool_name": self.name,
            "status": "success",
            "count": len(apps),
        })
        return ToolResult(
            success=True,
            output={
                "allowed_applications": apps,
                "note": "JARVIS can launch any installed desktop application, browser, utility, or tool on this system.",
            },
        )


class OpenApplicationTool(BaseTool):
    """Tool to safely open any application installed on the system."""

    name = "open_application"
    description = (
        "Launches any installed application on the system by name, executable, or shortcut "
        "(e.g., 'notepad', 'calculator', 'chrome', 'brave', 'explorer', 'excel', 'word', 'paint', 'antigravity', 'vlc')."
    )
    risk_level = RiskLevel.LOW
    requires_confirmation = False

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name or executable of the application to launch (e.g., 'notepad', 'chrome', 'calculator', 'explorer').",
                },
            },
            "required": ["app_name"],
            "additionalProperties": False,
        }

    def _resolve_from_app_paths(self, query: str) -> Optional[str]:
        """Search Windows Registry App Paths (HKLM and HKCU)."""
        if not winreg:
            return None

        candidates = [query, f"{query}.exe"]
        for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for cand in candidates:
                try:
                    key = winreg.OpenKey(
                        root,
                        rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{cand}",
                    )
                    val, _ = winreg.QueryValueEx(key, "")
                    clean_val = val.strip('\"')
                    if os.path.isfile(clean_val):
                        return clean_val
                except OSError:
                    pass
        return None

    def _resolve_from_start_menu(self, query: str) -> Optional[str]:
        """Search Start Menu shortcuts (.lnk files)."""
        start_dirs = [
            Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        ]
        q_clean = query.lower().strip()

        # Exact stem match first, then partial match
        for d in start_dirs:
            if not d.exists():
                continue
            for lnk in d.rglob("*.lnk"):
                if lnk.stem.lower() == q_clean:
                    return str(lnk)

        for d in start_dirs:
            if not d.exists():
                continue
            for lnk in d.rglob("*.lnk"):
                if q_clean in lnk.stem.lower():
                    return str(lnk)
        return None

    def resolve_application(self, app_name: str) -> Optional[Tuple[str, str, str]]:
        """Resolve app_name across Aliases, PATH, App Paths, and Start Menu.

        Returns: (target_path, display_name, launch_method) or None.
        """
        clean_name = app_name.strip()
        lower_name = clean_name.lower()

        # 1. Direct path check
        if os.path.isfile(clean_name):
            return clean_name, Path(clean_name).stem.title(), "process"

        # 2. Known system aliases
        if lower_name in KNOWN_SYSTEM_APPS:
            meta = KNOWN_SYSTEM_APPS[lower_name]
            raw_exe = meta["executable"]
            if raw_exe.startswith("ms-"):
                return raw_exe, meta["display_name"], "uri"
            # Resolve with shutil.which if needed
            resolved = shutil.which(raw_exe) if not os.path.isabs(raw_exe) else raw_exe
            if resolved and os.path.exists(resolved):
                return resolved, meta["display_name"], "process"
            return raw_exe, meta["display_name"], "process"

        # 3. System PATH check
        path_match = shutil.which(clean_name) or shutil.which(f"{clean_name}.exe")
        if path_match and os.path.isfile(path_match):
            return path_match, Path(path_match).stem.title(), "process"

        # 4. Windows App Paths registry check
        app_path_match = self._resolve_from_app_paths(lower_name)
        if app_path_match:
            return app_path_match, Path(app_path_match).stem.title(), "process"

        # 5. Start Menu shortcut check
        lnk_match = self._resolve_from_start_menu(lower_name)
        if lnk_match:
            return lnk_match, Path(lnk_match).stem, "shell"

        return None

    def execute(self, **kwargs: Any) -> ToolResult:
        app_name = (
            kwargs.get("app_name")
            or kwargs.get("application")
            or kwargs.get("app")
            or kwargs.get("name")
        )

        if not app_name or not isinstance(app_name, str):
            err_msg = "Parameter 'app_name' must be a non-empty string."
            logger.error(err_msg)
            return ToolResult(
                success=False,
                error=err_msg,
                output={"success": False, "application": str(app_name), "error": err_msg},
            )

        resolution = self.resolve_application(app_name)
        if not resolution:
            err_msg = f"Application '{app_name}' could not be found on this system."
            logger.warning(err_msg)
            audit_logger.log_event("TOOL_EXECUTION_DENIED", {
                "tool_name": self.name,
                "app_name": app_name,
                "reason": err_msg,
            }, level=logging.WARNING)
            return ToolResult(
                success=False,
                error=err_msg,
                output={"success": False, "application": app_name, "error": err_msg},
            )

        target, display_name, launch_method = resolution
        logger.debug(f"Application requested: {app_name}")
        logger.debug(f"Resolved target: {target}")
        logger.debug(f"Launch method: {launch_method}")

        try:
            active_pid = None
            if launch_method == "uri" or launch_method == "shell":
                # Launch via Windows shell (shortcuts or URI schemes)
                os.startfile(target)
                time.sleep(0.5)
                # Check for matching active process
                for proc in psutil.process_iter(["pid", "name"]):
                    if display_name.lower() in proc.info.get("name", "").lower():
                        active_pid = proc.info["pid"]
                        break
            else:
                # Direct process execution
                process = subprocess.Popen(
                    [target],
                    close_fds=True,
                )
                pid = process.pid
                time.sleep(0.3)
                poll_status = process.poll()
                is_running = psutil.pid_exists(pid) if pid else False

                active_pid = pid
                if is_running and poll_status is None:
                    active_pid = pid
                elif poll_status == 0 or not is_running:
                    # Windows Store / Execution Alias stub delegation
                    target_stem = Path(target).stem.lower()
                    for proc in psutil.process_iter(["pid", "name"]):
                        p_name = proc.info.get("name", "").lower()
                        if target_stem in p_name or display_name.lower() in p_name:
                            active_pid = proc.info["pid"]
                            is_running = True
                            break

                if poll_status is not None and poll_status != 0:
                    err_msg = f"Process '{display_name}' exited immediately with code {poll_status}."
                    logger.error(err_msg)
                    return ToolResult(
                        success=False,
                        error=err_msg,
                        output={
                            "success": False,
                            "application": display_name,
                            "executable": target,
                            "pid": pid,
                            "error": err_msg,
                        },
                    )

            msg = f"{display_name} launched successfully."
            audit_logger.log_event("TOOL_EXECUTION", {
                "tool_name": self.name,
                "app_name": display_name,
                "target": target,
                "pid": active_pid,
                "status": "success",
            })

            return ToolResult(
                success=True,
                output={
                    "success": True,
                    "application": display_name,
                    "pid": active_pid,
                    "executable": target,
                    "message": msg,
                },
            )
        except Exception as exc:
            err_msg = f"Failed to launch '{display_name}': {str(exc)}"
            logger.error(err_msg)
            return ToolResult(
                success=False,
                error=err_msg,
                output={
                    "success": False,
                    "application": display_name,
                    "error": err_msg,
                },
            )
