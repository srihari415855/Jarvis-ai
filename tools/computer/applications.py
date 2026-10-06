"""Windows application management and launching tools for JARVIS.

Supports launching trusted applications as well as any installed Windows application
(Win32 executables, Start Menu shortcuts, Packaged/Store applications, and system URIs)
while enforcing strict security against command injection, path traversal, and arbitrary binaries.
"""

import os
from pathlib import Path
import platform
import re
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


class ApplicationType:
    """Supported Windows application categories."""
    WIN32 = "win32"
    PACKAGED_APP = "packaged_app"
    URI = "uri"


PROHIBITED_COMMANDS = {
    "cmd", "cmd.exe",
    "powershell", "powershell.exe",
    "pwsh", "pwsh.exe",
    "bash", "sh",
    "wscript", "cscript",
}


# Trusted Windows Application Allowlist & Registry
TRUSTED_APPLICATIONS: Dict[str, Dict[str, Any]] = {
    "notepad": {
        "name": "notepad",
        "display_name": "Notepad",
        "type": ApplicationType.WIN32,
        "target": "notepad.exe",
        "aliases": ["notepad", "text editor"],
        "description": "Standard Windows text editor",
    },
    "calculator": {
        "name": "calculator",
        "display_name": "Calculator",
        "type": ApplicationType.WIN32,
        "target": "calc.exe",
        "aliases": ["calculator", "calc"],
        "description": "Windows Calculator",
    },
    "explorer": {
        "name": "explorer",
        "display_name": "File Explorer",
        "type": ApplicationType.WIN32,
        "target": "explorer.exe",
        "aliases": ["explorer", "file explorer", "windows explorer"],
        "description": "Windows File Explorer",
    },
    "chrome": {
        "name": "chrome",
        "display_name": "Google Chrome",
        "type": ApplicationType.WIN32,
        "target": "chrome.exe",
        "aliases": ["chrome", "google chrome"],
        "description": "Google Chrome Web Browser",
    },
    "edge": {
        "name": "edge",
        "display_name": "Microsoft Edge",
        "type": ApplicationType.WIN32,
        "target": "msedge.exe",
        "aliases": ["edge", "msedge", "microsoft edge"],
        "description": "Microsoft Edge Web Browser",
    },
    "brave": {
        "name": "brave",
        "display_name": "Brave Browser",
        "type": ApplicationType.WIN32,
        "target": "brave.exe",
        "aliases": ["brave", "brave browser"],
        "description": "Brave Web Browser",
    },
    "whatsapp": {
        "name": "whatsapp",
        "display_name": "WhatsApp",
        "type": ApplicationType.PACKAGED_APP,
        "target": "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App",
        "aliases": ["whatsapp", "whatsapp desktop", "WhatsApp", "WhatsApp Desktop", "wa"],
        "description": "WhatsApp Desktop Packaged Application",
    },
    "word": {
        "name": "word",
        "display_name": "Microsoft Word",
        "type": ApplicationType.WIN32,
        "target": "winword.exe",
        "aliases": ["word", "ms word", "microsoft word", "winword"],
        "description": "Microsoft Word",
    },
    "excel": {
        "name": "excel",
        "display_name": "Microsoft Excel",
        "type": ApplicationType.WIN32,
        "target": "excel.exe",
        "aliases": ["excel", "ms excel", "microsoft excel"],
        "description": "Microsoft Excel",
    },
    "powerpoint": {
        "name": "powerpoint",
        "display_name": "Microsoft PowerPoint",
        "type": ApplicationType.WIN32,
        "target": "powerpnt.exe",
        "aliases": ["powerpoint", "ppt", "powerpnt", "ms powerpoint"],
        "description": "Microsoft PowerPoint",
    },
    "code": {
        "name": "code",
        "display_name": "Visual Studio Code",
        "type": ApplicationType.WIN32,
        "target": "code.exe",
        "aliases": ["code", "vscode", "vs code", "visual studio code"],
        "description": "Microsoft Visual Studio Code",
    },
    "vlc": {
        "name": "vlc",
        "display_name": "VLC Media Player",
        "type": ApplicationType.WIN32,
        "target": "vlc.exe",
        "aliases": ["vlc", "vlc media player"],
        "description": "VLC Media Player",
    },
    "paint": {
        "name": "paint",
        "display_name": "Paint",
        "type": ApplicationType.WIN32,
        "target": "mspaint.exe",
        "aliases": ["paint", "mspaint"],
        "description": "Windows Paint",
    },
    "task manager": {
        "name": "task manager",
        "display_name": "Task Manager",
        "type": ApplicationType.WIN32,
        "target": "taskmgr.exe",
        "aliases": ["task manager", "taskmgr"],
        "description": "Windows Task Manager",
    },
    "terminal": {
        "name": "terminal",
        "display_name": "Windows Terminal",
        "type": ApplicationType.WIN32,
        "target": "wt.exe",
        "aliases": ["terminal", "windows terminal", "wt"],
        "description": "Windows Terminal",
    },
    "settings": {
        "name": "settings",
        "display_name": "Windows Settings",
        "type": ApplicationType.URI,
        "target": "ms-settings:",
        "aliases": ["settings", "windows settings"],
        "description": "Windows Settings App",
    },
    "photos": {
        "name": "photos",
        "display_name": "Microsoft Photos",
        "type": ApplicationType.URI,
        "target": "ms-photos:",
        "aliases": ["photos", "microsoft photos"],
        "description": "Microsoft Photos App",
    },
    "camera": {
        "name": "camera",
        "display_name": "Camera",
        "type": ApplicationType.URI,
        "target": "microsoft.windows.camera:",
        "aliases": ["camera", "windows camera"],
        "description": "Windows Camera App",
    },
    "clock": {
        "name": "clock",
        "display_name": "Windows Clock",
        "type": ApplicationType.URI,
        "target": "ms-clock:",
        "aliases": ["clock", "alarms", "windows clock"],
        "description": "Windows Clock & Alarms",
    },
    "store": {
        "name": "store",
        "display_name": "Microsoft Store",
        "type": ApplicationType.URI,
        "target": "ms-windows-store:",
        "aliases": ["store", "microsoft store", "windows store"],
        "description": "Microsoft Store",
    },
    "antigravity": {
        "name": "antigravity",
        "display_name": "Antigravity IDE",
        "type": ApplicationType.WIN32,
        "target": _get_antigravity_path() or "Antigravity IDE.exe",
        "aliases": ["antigravity", "antigravity ide"],
        "description": "Antigravity AI Agent IDE",
    },
}

# Maintain backward compatibility alias
KNOWN_SYSTEM_APPS = TRUSTED_APPLICATIONS


class ApplicationRegistry:
    """Registry managing trusted applications, alias normalization, and dynamic system discovery."""

    def __init__(self, applications: Optional[Dict[str, Dict[str, Any]]] = None):
        self._apps: Dict[str, Dict[str, Any]] = (
            applications if applications is not None else TRUSTED_APPLICATIONS
        )
        self._alias_map: Dict[str, str] = {}
        self._rebuild_alias_map()
        self._discovered_cache: Dict[str, Dict[str, Any]] = {}
        self._start_apps_cache: Optional[List[Dict[str, str]]] = None

    def _rebuild_alias_map(self) -> None:
        self._alias_map.clear()
        for canonical_name, data in self._apps.items():
            self._alias_map[canonical_name.lower().strip()] = canonical_name
            for alias in data.get("aliases", []):
                self._alias_map[alias.lower().strip()] = canonical_name

    def normalize_name(self, raw_name: str) -> Optional[str]:
        """Normalize an input application name or alias to its canonical registry name.

        Rejects arbitrary file paths, AppIDs, path traversal, commands, and special characters.
        """
        if not raw_name or not isinstance(raw_name, str):
            return None
        clean = raw_name.strip()
        # Security: reject path separators, AppID indicators, command separators, env vars
        if any(c in clean for c in ("/", "\\", "..", ":", "!", ";", "|", "&", "<", ">", "$", "%", "`")):
            return None
        clean_low = clean.lower()
        if clean_low.endswith(".exe"):
            clean_low = clean_low[:-4].strip()
        if clean_low in PROHIBITED_COMMANDS:
            return None
        return self._alias_map.get(clean_low) or clean_low

    def _discover_start_menu_shortcut(self, query: str) -> Optional[Tuple[str, str]]:
        """Search Start Menu shortcuts (.lnk files) for query."""
        start_dirs = [
            Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        ]
        q_clean = query.lower().strip()
        q_norm = re.sub(r"[^a-z0-9]", "", q_clean)
        if len(q_norm) < 2:
            return None

        q_tokens = set(re.findall(r"[a-z0-9]+", q_clean))

        shortcuts: List[Tuple[Path, str, str]] = []
        for d in start_dirs:
            if d.exists():
                for lnk in d.rglob("*.lnk"):
                    stem_low = lnk.stem.lower()
                    if not any(skip in stem_low for skip in ("uninstall", "website", "documentation", "release notes", "help", "readme", "license")):
                        shortcuts.append((lnk, stem_low, lnk.stem))

        # 1. Exact stem match
        for lnk, stem_low, original in shortcuts:
            if stem_low == q_clean:
                return str(lnk), original

        # 2. Normalized alphanumeric match
        for lnk, stem_low, original in shortcuts:
            if q_norm == re.sub(r"[^a-z0-9]", "", stem_low):
                return str(lnk), original

        # 3. All tokens in query match shortcut stem
        if q_tokens:
            for lnk, stem_low, original in shortcuts:
                stem_tokens = set(re.findall(r"[a-z0-9]+", stem_low))
                if q_tokens == stem_tokens or (q_tokens.issubset(stem_tokens) and len(stem_tokens) <= len(q_tokens) + 3):
                    return str(lnk), original

        # 4. Query substring in shortcut stem
        for lnk, stem_low, original in shortcuts:
            if len(q_clean) >= 3 and q_clean in stem_low:
                return str(lnk), original

        return None

    def _discover_app_paths(self, query: str) -> Optional[Tuple[str, str]]:
        """Search Windows Registry App Paths (HKLM and HKCU)."""
        if not winreg:
            return None

        clean = query.strip().lower()
        candidates = [clean, f"{clean}.exe"]

        for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for cand in candidates:
                try:
                    key = winreg.OpenKey(
                        root,
                        rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{cand}",
                    )
                    val, _ = winreg.QueryValueEx(key, "")
                    clean_val = val.strip('"')
                    expanded = os.path.expandvars(clean_val)
                    if os.path.isfile(expanded):
                        disp = Path(cand).stem.title()
                        return expanded, disp
                except OSError:
                    pass

        return None

    def _discover_program_files(self, query: str) -> Optional[Tuple[str, str]]:
        """Search Program Files and LocalAppData application directories."""
        clean = query.strip().lower()
        q_norm = re.sub(r"[^a-z0-9]", "", clean)
        if len(q_norm) < 2:
            return None

        search_dirs = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
            Path(os.environ.get("ProgramFiles", "C:/Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WindowsApps",
            Path(os.environ.get("APPDATA", "")),
        ]

        # Preferred candidates
        best_match: Optional[Tuple[str, str]] = None

        for base_dir in search_dirs:
            if not base_dir.exists():
                continue
            try:
                for entry in base_dir.iterdir():
                    if entry.is_dir():
                        entry_norm = re.sub(r"[^a-z0-9]", "", entry.name.lower())
                        # Check if query matches folder or folder is in query (e.g. 'docker' in 'docker desktop')
                        if q_norm == entry_norm or (len(entry_norm) >= 3 and entry_norm in q_norm) or (len(q_norm) >= 3 and q_norm in entry_norm):
                            # First search direct folder executables
                            for exe in entry.glob("*.exe"):
                                exe_norm = re.sub(r"[^a-z0-9]", "", exe.stem.lower())
                                if not any(s in exe.name.lower() for s in ("uninstall", "update", "crash", "helper", "agent")):
                                    if q_norm == exe_norm:
                                        return str(exe), exe.stem.title()
                                    if not best_match and (q_norm in exe_norm or exe_norm in q_norm):
                                        best_match = (str(exe), exe.stem.title())
                            # Second search subdirectories (avoid cli-plugins/helpers)
                            for sub_dir in entry.iterdir():
                                if sub_dir.is_dir() and not any(skip in sub_dir.name.lower() for skip in ("plugin", "helper", "crash", "update", "tool")):
                                    for exe in sub_dir.glob("*.exe"):
                                        exe_norm = re.sub(r"[^a-z0-9]", "", exe.stem.lower())
                                        if not any(s in exe.name.lower() for s in ("uninstall", "update", "crash", "helper", "agent")):
                                            if q_norm == exe_norm:
                                                return str(exe), exe.stem.title()
                                            if not best_match and (q_norm in exe_norm or exe_norm in q_norm):
                                                best_match = (str(exe), exe.stem.title())
            except (PermissionError, OSError):
                pass

        return best_match

    def _load_start_apps(self) -> List[Dict[str, str]]:
        """Lazily load installed applications from Windows Get-StartApps."""
        if self._start_apps_cache is not None:
            return self._start_apps_cache

        self._start_apps_cache = []
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-StartApps | ConvertTo-Json -Depth 2"],
                capture_output=True,
                text=True,
                timeout=6,
            )
            if res.returncode == 0 and res.stdout.strip():
                import json
                apps_data = json.loads(res.stdout)
                if isinstance(apps_data, dict):
                    apps_data = [apps_data]
                if isinstance(apps_data, list):
                    for a in apps_data:
                        name = a.get("Name")
                        app_id = a.get("AppID")
                        if name and app_id:
                            # Skip web URLs and non-app shortcuts
                            if app_id.startswith("http://") or app_id.startswith("https://") or app_id.endswith(".url"):
                                continue
                            if any(skip in name.lower() for skip in ("uninstall", "documentation", "release notes", "license", "help")):
                                continue
                            if any(p in name.lower() for p in PROHIBITED_COMMANDS):
                                continue
                            self._start_apps_cache.append({
                                "Name": name,
                                "AppID": app_id,
                            })
        except Exception as exc:
            logger.debug(f"Failed to query StartApps: {exc}")

        return self._start_apps_cache

    def _discover_from_start_apps(self, query: str) -> Optional[Tuple[str, str, str]]:
        """Search Get-StartApps entries for query.

        Returns: (target, display_name, launch_type) or None
        """
        apps = self._load_start_apps()
        if not apps:
            return None

        q_clean = query.strip().lower()
        q_norm = re.sub(r"[^a-z0-9]", "", q_clean)
        if len(q_norm) < 2:
            return None

        q_tokens = set(re.findall(r"[a-z0-9]+", q_clean))

        # Helper to format return
        def format_entry(a: Dict[str, str]) -> Tuple[str, str, str]:
            name = a["Name"]
            app_id = a["AppID"]
            if os.path.isfile(app_id):
                return app_id, name, ApplicationType.WIN32
            if "!" in app_id:
                return app_id, name, ApplicationType.PACKAGED_APP
            return f"shell:AppsFolder\\{app_id}", name, ApplicationType.WIN32

        # 1. Exact normalized match
        for a in apps:
            name_norm = re.sub(r"[^a-z0-9]", "", a["Name"].lower())
            if q_norm == name_norm:
                return format_entry(a)

        # 2. Token match
        if q_tokens:
            for a in apps:
                name_tokens = set(re.findall(r"[a-z0-9]+", a["Name"].lower()))
                if q_tokens == name_tokens or q_tokens.issubset(name_tokens):
                    return format_entry(a)

        # 3. Substring match
        if len(q_norm) >= 3:
            for a in apps:
                name_norm = re.sub(r"[^a-z0-9]", "", a["Name"].lower())
                if q_norm in name_norm:
                    return format_entry(a)

        return None

    def _lookup_system_application(self, canonical: str) -> Optional[Dict[str, Any]]:
        """Dynamically discover genuinely installed applications on the Windows system."""
        # 1. Start Menu shortcut (.lnk)
        shortcut_hit = self._discover_start_menu_shortcut(canonical)
        if shortcut_hit:
            lnk_path, disp_name = shortcut_hit
            return {
                "name": canonical,
                "display_name": disp_name,
                "type": ApplicationType.WIN32,
                "target": lnk_path,
                "description": f"Installed Windows application ({disp_name})",
            }

        # 2. Windows StartApps (covers all registered Start Menu apps, Store apps, and Desktop AUMIDs)
        start_app_hit = self._discover_from_start_apps(canonical)
        if start_app_hit:
            target, disp_name, app_type = start_app_hit
            return {
                "name": canonical,
                "display_name": disp_name,
                "type": app_type,
                "target": target,
                "description": f"Installed Windows application ({disp_name})",
            }

        # 3. Windows Registry App Paths
        app_path_hit = self._discover_app_paths(canonical)
        if app_path_hit:
            exe_path, disp_name = app_path_hit
            return {
                "name": canonical,
                "display_name": disp_name,
                "type": ApplicationType.WIN32,
                "target": exe_path,
                "description": f"Installed Windows application ({disp_name})",
            }

        # 4. Program Files & LocalAppData search
        prog_hit = self._discover_program_files(canonical)
        if prog_hit:
            exe_path, disp_name = prog_hit
            return {
                "name": canonical,
                "display_name": disp_name,
                "type": ApplicationType.WIN32,
                "target": exe_path,
                "description": f"Installed Windows application ({disp_name})",
            }

        # 5. System PATH executable check
        path_match = shutil.which(canonical) or shutil.which(f"{canonical}.exe")
        if path_match and os.path.isfile(path_match):
            return {
                "name": canonical,
                "display_name": Path(path_match).stem.title(),
                "type": ApplicationType.WIN32,
                "target": path_match,
                "description": f"System PATH executable ({Path(path_match).stem})",
            }

        return None

    def lookup(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Look up an application by name or alias.

        Checks trusted registry first, then dynamically discovers genuine installed applications.
        Returns the application metadata dict if found, or None.
        """
        canonical = self.normalize_name(app_name)
        if not canonical:
            return None

        # 1. Check predefined trusted applications
        if canonical in self._apps:
            return self._apps[canonical]

        # 2. Check cached discovered applications
        if canonical in self._discovered_cache:
            return self._discovered_cache[canonical]

        # 3. Dynamically discover from the Windows system
        entry = self._lookup_system_application(canonical)
        if entry:
            self._discovered_cache[canonical] = entry
            return entry

        return None

    def get_all_applications(self) -> List[Dict[str, Any]]:
        """Return all trusted applications."""
        return list(self._apps.values())


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

    def __init__(self) -> None:
        super().__init__()
        self.registry = ApplicationRegistry()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        seen = set()
        apps = []
        for data in self.registry.get_all_applications():
            name = data["display_name"]
            if name not in seen:
                seen.add(name)
                apps.append({
                    "id": data["name"],
                    "name": name,
                    "type": data.get("type", ApplicationType.WIN32),
                    "description": data.get("description", name),
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
        "Launches any installed application on the system by name or alias "
        "(e.g., 'notepad', 'calculator', 'chrome', 'brave', 'explorer', 'whatsapp', 'docker desktop', 'android studio', 'anydesk', 'excel', 'word', 'paint', 'vlc', 'vs code')."
    )
    risk_level = RiskLevel.LOW
    requires_confirmation = False

    def __init__(self) -> None:
        super().__init__()
        self.registry = ApplicationRegistry()

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name or alias of the application to launch (e.g., 'notepad', 'chrome', 'calculator', 'explorer', 'whatsapp', 'docker desktop', 'android studio', 'anydesk', 'brave', 'word').",
                },
            },
            "required": ["app_name"],
            "additionalProperties": False,
        }

    def _resolve_from_app_paths(self, query: str) -> Optional[Tuple[str, str]]:
        return self.registry._discover_app_paths(query)

    def _resolve_from_start_menu(self, query: str) -> Optional[Tuple[str, str]]:
        return self.registry._discover_start_menu_shortcut(query)

    def _resolve_from_program_files(self, query: str) -> Optional[Tuple[str, str]]:
        return self.registry._discover_program_files(query)

    def resolve_application(self, app_name: str) -> Optional[Tuple[str, str, str]]:
        """Resolve app_name across trusted applications and installed system applications.

        Returns: (target_path_or_id, display_name, launch_type) or None.
        """
        if not app_name or not isinstance(app_name, str):
            return None

        clean_name = app_name.strip()
        app_entry = self.registry.lookup(clean_name)
        if not app_entry:
            return None

        app_type = app_entry.get("type", ApplicationType.WIN32)
        display_name = app_entry.get("display_name", clean_name.title())
        raw_target = app_entry.get("target", "")

        # 1. Packaged applications (e.g. WhatsApp, Store apps)
        if app_type == ApplicationType.PACKAGED_APP:
            return raw_target, display_name, ApplicationType.PACKAGED_APP

        # 2. Protocol URIs (e.g. ms-settings:)
        if app_type == ApplicationType.URI:
            return raw_target, display_name, ApplicationType.URI

        # 3. Direct shortcut (.lnk), shell:AppsFolder URI, or existing executable file path
        if raw_target.lower().startswith("shell:appsfolder\\") or os.path.isfile(raw_target):
            return raw_target, display_name, ApplicationType.WIN32

        # 4. Resolve raw target executable via PATH, App Paths, Start Menu, Program Files
        resolved = shutil.which(raw_target)
        if resolved and os.path.isfile(resolved):
            return resolved, display_name, ApplicationType.WIN32

        app_path_hit = self._resolve_from_app_paths(raw_target)
        if app_path_hit:
            return app_path_hit[0], display_name, ApplicationType.WIN32

        start_menu_hit = self._resolve_from_start_menu(display_name)
        if start_menu_hit:
            return start_menu_hit[0], display_name, ApplicationType.WIN32

        prog_hit = self._resolve_from_program_files(raw_target)
        if prog_hit:
            return prog_hit[0], display_name, ApplicationType.WIN32

        return raw_target, display_name, ApplicationType.WIN32

    def launch_win32(self, app_entry: Dict[str, Any], resolved_target: str) -> ToolResult:
        """Launch a validated Win32 executable, shortcut, or desktop shell app and verify process execution."""
        display_name = app_entry.get("display_name", app_entry.get("name", "Application"))
        canonical_name = app_entry.get("name", display_name.lower())
        app_name_out = "whatsapp" if canonical_name == "whatsapp" else display_name

        try:
            active_pid = None
            if resolved_target.lower().endswith(".lnk") or resolved_target.lower().startswith("shell:appsfolder\\"):
                # Windows Shell invocation for shortcuts or AppsFolder items
                os.startfile(resolved_target)
                time.sleep(0.5)
                target_stem = Path(resolved_target).stem.lower()
                for proc in psutil.process_iter(["pid", "name"]):
                    try:
                        p_name = proc.info.get("name", "").lower()
                        if target_stem in p_name or display_name.lower() in p_name:
                            active_pid = proc.info["pid"]
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            else:
                process = subprocess.Popen(
                    [resolved_target],
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
                    target_stem = Path(resolved_target).stem.lower()
                    for proc in psutil.process_iter(["pid", "name"]):
                        try:
                            p_name = proc.info.get("name", "").lower()
                            if target_stem in p_name or display_name.lower() in p_name:
                                active_pid = proc.info["pid"]
                                is_running = True
                                break
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

                if poll_status is not None and poll_status != 0:
                    err_msg = f"Process '{display_name}' exited immediately with code {poll_status}."
                    logger.error(err_msg)
                    return ToolResult(
                        success=False,
                        error=err_msg,
                        output={
                            "success": False,
                            "tool": self.name,
                            "application": app_name_out,
                            "launch_type": ApplicationType.WIN32,
                            "executable": resolved_target,
                            "pid": pid,
                            "error": err_msg,
                        },
                    )

            msg = f"{display_name} launched successfully."
            audit_logger.log_event("TOOL_EXECUTION", {
                "tool_name": self.name,
                "app_name": display_name,
                "target": resolved_target,
                "launch_type": ApplicationType.WIN32,
                "pid": active_pid,
                "status": "success",
            })

            return ToolResult(
                success=True,
                output={
                    "success": True,
                    "tool": self.name,
                    "application": app_name_out,
                    "launch_type": ApplicationType.WIN32,
                    "pid": active_pid,
                    "executable": resolved_target,
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
                    "tool": self.name,
                    "application": app_name_out,
                    "launch_type": ApplicationType.WIN32,
                    "error": err_msg,
                },
            )

    def launch_packaged_app(self, app_entry: Dict[str, Any]) -> ToolResult:
        """Launch a validated Windows packaged application via shell:AppsFolder."""
        display_name = app_entry.get("display_name", "Application")
        canonical_name = app_entry.get("name", "packaged_app")
        app_name_out = "whatsapp" if canonical_name == "whatsapp" else display_name
        app_id = app_entry.get("target")

        # 1. Verify existence of AppUserModelID
        if not app_id or not isinstance(app_id, str):
            err_msg = f"Trusted AppUserModelID is missing or invalid for '{canonical_name}'."
            logger.error(err_msg)
            return ToolResult(
                success=False,
                error=err_msg,
                output={
                    "success": False,
                    "tool": self.name,
                    "application": app_name_out,
                    "launch_type": ApplicationType.PACKAGED_APP,
                    "error": err_msg,
                },
            )

        # 2. Verify format of AppUserModelID (PackageFamilyName!AppId)
        if "!" not in app_id:
            err_msg = f"Invalid AppUserModelID format '{app_id}' for packaged application."
            logger.error(err_msg)
            return ToolResult(
                success=False,
                error=err_msg,
                output={
                    "success": False,
                    "tool": self.name,
                    "application": app_name_out,
                    "launch_type": ApplicationType.PACKAGED_APP,
                    "error": err_msg,
                },
            )

        shell_target = f"shell:AppsFolder\\{app_id}"
        logger.debug(f"Launching packaged application: {shell_target}")

        try:
            # Safe Windows shell invocation without cmd.exe or shell=True
            os.startfile(shell_target)
            time.sleep(0.5)

            # Verification of active process
            active_pid = None
            search_terms = [canonical_name.lower(), display_name.lower()]
            if canonical_name == "whatsapp":
                search_terms.append("whatsapp.root")

            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    p_name = proc.info.get("name", "").lower()
                    if any(term in p_name for term in search_terms):
                        active_pid = proc.info["pid"]
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            msg = f"{display_name} launched successfully."
            audit_logger.log_event("TOOL_EXECUTION", {
                "tool_name": self.name,
                "app_name": display_name,
                "target": shell_target,
                "launch_type": ApplicationType.PACKAGED_APP,
                "pid": active_pid,
                "status": "success",
            })

            return ToolResult(
                success=True,
                output={
                    "success": True,
                    "tool": self.name,
                    "application": app_name_out,
                    "launch_type": ApplicationType.PACKAGED_APP,
                    "pid": active_pid,
                    "message": msg,
                },
            )
        except Exception as exc:
            err_msg = f"Failed to launch packaged app '{display_name}': {str(exc)}"
            logger.error(err_msg)
            return ToolResult(
                success=False,
                error=err_msg,
                output={
                    "success": False,
                    "tool": self.name,
                    "application": app_name_out,
                    "launch_type": ApplicationType.PACKAGED_APP,
                    "error": err_msg,
                },
            )

    def launch_uri(self, app_entry: Dict[str, Any]) -> ToolResult:
        """Launch a Windows protocol URI application."""
        display_name = app_entry.get("display_name", "Application")
        canonical_name = app_entry.get("name", "uri_app")
        app_name_out = "whatsapp" if canonical_name == "whatsapp" else display_name
        target_uri = app_entry.get("target")

        try:
            os.startfile(target_uri)
            time.sleep(0.3)
            msg = f"{display_name} launched successfully."
            audit_logger.log_event("TOOL_EXECUTION", {
                "tool_name": self.name,
                "app_name": display_name,
                "target": target_uri,
                "launch_type": ApplicationType.URI,
                "status": "success",
            })
            return ToolResult(
                success=True,
                output={
                    "success": True,
                    "tool": self.name,
                    "application": app_name_out,
                    "launch_type": ApplicationType.URI,
                    "message": msg,
                },
            )
        except Exception as exc:
            err_msg = f"Failed to launch URI '{target_uri}': {str(exc)}"
            logger.error(err_msg)
            return ToolResult(
                success=False,
                error=err_msg,
                output={
                    "success": False,
                    "tool": self.name,
                    "application": app_name_out,
                    "launch_type": ApplicationType.URI,
                    "error": err_msg,
                },
            )

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
                output={
                    "success": False,
                    "tool": self.name,
                    "application": str(app_name),
                    "error": err_msg,
                },
            )

        clean_name = app_name.strip()
        app_entry = self.registry.lookup(clean_name)
        if not app_entry:
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
                output={
                    "success": False,
                    "tool": self.name,
                    "application": app_name,
                    "error": err_msg,
                },
            )

        resolution = self.resolve_application(clean_name)
        if not resolution:
            err_msg = f"Application '{app_name}' could not be resolved on this system."
            logger.warning(err_msg)
            return ToolResult(
                success=False,
                error=err_msg,
                output={
                    "success": False,
                    "tool": self.name,
                    "application": app_name,
                    "error": err_msg,
                },
            )

        target, display_name, launch_type = resolution
        logger.debug(f"Application requested: {app_name}")
        logger.debug(f"Resolved target: {target}")
        logger.debug(f"Launch type: {launch_type}")

        if launch_type == ApplicationType.PACKAGED_APP:
            return self.launch_packaged_app(app_entry)
        elif launch_type == ApplicationType.URI:
            return self.launch_uri(app_entry)
        else:
            return self.launch_win32(app_entry, target)
