"""Unit tests for OpenApplicationTool and Windows Application Registry.
"""

import unittest
from unittest.mock import MagicMock, patch
from tools.computer.applications import (
    ApplicationRegistry,
    ApplicationType,
    OpenApplicationTool,
)


class TestOpenApplicationTool(unittest.TestCase):

    def setUp(self):
        self.tool = OpenApplicationTool()
        self.registry = ApplicationRegistry()

    def test_schema_validity(self):
        schema = self.tool.get_parameters_schema()
        assert schema["type"] == "object"
        assert "app_name" in schema["required"]

    def test_missing_app_name(self):
        result = self.tool.execute()
        assert not result.success
        assert "Parameter 'app_name' must be a non-empty string" in result.error

    @patch("subprocess.Popen")
    @patch("psutil.pid_exists", return_value=True)
    def test_successful_launch(self, mock_pid_exists, mock_popen):
        mock_process = MagicMock()
        mock_process.pid = 9999
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        result = self.tool.execute(app_name="notepad")
        assert result.success
        assert result.output["pid"] == 9999
        assert result.output["application"] == "Notepad"
        assert result.output["launch_type"] == ApplicationType.WIN32

    def test_unknown_app_rejected(self):
        result = self.tool.execute(app_name="unknown_nonexistent_binary_xyz")
        assert not result.success
        assert "could not be found" in result.error

    def test_resolve_popular_applications(self):
        # Verify resolution on Windows system
        for app in ["notepad", "calculator", "explorer", "paint", "brave", "chrome", "edge", "vs code", "word", "vlc"]:
            res = self.tool.resolve_application(app)
            assert res is not None, f"Failed to resolve {app}"
            target, display_name, method = res
            assert len(target) > 0
            assert len(display_name) > 0
            assert method in ("win32", "packaged_app", "uri", "process", "shell")

    @patch("subprocess.Popen")
    @patch("psutil.pid_exists", return_value=True)
    def test_launch_brave_browser(self, mock_pid_exists, mock_popen):
        mock_process = MagicMock()
        mock_process.pid = 8888
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        result = self.tool.execute(app_name="brave")
        assert result.success is True
        assert result.output["application"] == "Brave Browser"
        assert "brave" in result.output["executable"].lower()

    # --- New Tests for Windows Packaged Application & Security Requirements ---

    def test_win32_application_resolution(self):
        """Win32 application resolution produces correct target and win32 type."""
        for app_name, expected_frag in [
            ("notepad", "notepad"),
            ("chrome", "chrome"),
            ("explorer", "explorer"),
        ]:
            res = self.tool.resolve_application(app_name)
            assert res is not None, f"Expected {app_name} to resolve"
            target, display_name, launch_type = res
            assert launch_type == ApplicationType.WIN32
            assert expected_frag in target.lower()

    def test_packaged_application_resolution(self):
        """WhatsApp resolves strictly to packaged_app type and trusted AppUserModelID."""
        res = self.tool.resolve_application("whatsapp")
        assert res is not None
        target, display_name, launch_type = res
        assert launch_type == ApplicationType.PACKAGED_APP
        assert display_name == "WhatsApp"
        assert target == "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"

    def test_whatsapp_alias_normalization(self):
        """All WhatsApp aliases normalize to canonical name 'whatsapp'."""
        aliases = [
            "whatsapp",
            "WhatsApp",
            "WhatsApp Desktop",
            "whatsapp desktop",
            "wa",
            "  whatsapp  ",
        ]
        for alias in aliases:
            norm = self.registry.normalize_name(alias)
            assert norm == "whatsapp", f"Alias '{alias}' did not normalize to 'whatsapp' (got '{norm}')"
            entry = self.registry.lookup(alias)
            assert entry is not None
            assert entry["name"] == "whatsapp"
            assert entry["type"] == ApplicationType.PACKAGED_APP

    def test_trusted_appid_lookup(self):
        """WhatsApp lookup provides trusted AppUserModelID from registry, never arbitrary input."""
        entry = self.registry.lookup("whatsapp")
        assert entry is not None
        assert entry["target"] == "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"
        assert entry["type"] == ApplicationType.PACKAGED_APP

    def test_unknown_packaged_application_rejection(self):
        """Unknown or un-allowlisted packaged applications are rejected."""
        unknown_apps = [
            "fake_uwp_app",
            "SomeVendor.SomeApp_cv1g1gvanyjgm!App",
            "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
            "com.unknown.whatsapp",
        ]
        for app in unknown_apps:
            entry = self.registry.lookup(app)
            assert entry is None, f"Application '{app}' should have been rejected by registry"
            res = self.tool.resolve_application(app)
            assert res is None, f"Application '{app}' should have returned None from resolve_application"

    def test_arbitrary_appid_rejection(self):
        """Direct passing of arbitrary AppID strings must be rejected."""
        arbitrary_ids = [
            "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App",
            "Microsoft.Paint_8wekyb3d8bbwe!App",
            "Malicious.Package_cv1g1gvanyjgm!App",
            "RandomPackage!App",
        ]
        for app_id in arbitrary_ids:
            # Must be rejected by normalize_name and lookup
            assert self.registry.normalize_name(app_id) is None
            assert self.registry.lookup(app_id) is None
            result = self.tool.execute(app_name=app_id)
            assert result.success is False
            assert "could not be found" in result.error

    def test_invalid_application_rejection(self):
        """Arbitrary paths, shell interpreters, and invalid application names are rejected."""
        invalid_inputs = [
            r"C:\some\arbitrary.exe",
            r"..\..\Windows\System32\cmd.exe",
            "powershell",
            "cmd",
            "xyz123",
            "powershell.exe",
            "cmd.exe",
            "calc.exe && dir",
            "whatsapp; rm -rf /",
        ]
        for invalid_input in invalid_inputs:
            assert self.registry.lookup(invalid_input) is None
            result = self.tool.execute(app_name=invalid_input)
            assert result.success is False
            assert "could not be found" in result.error or "must be a non-empty string" in result.error

    @patch("os.startfile")
    @patch("psutil.process_iter")
    def test_whatsapp_packaged_launch_mocked(self, mock_process_iter, mock_startfile):
        """Launching WhatsApp invokes shell:AppsFolder with trusted AppID and returns structured result."""
        mock_proc = MagicMock()
        mock_proc.info = {"pid": 24680, "name": "WhatsApp.Root.exe"}
        mock_process_iter.return_value = [mock_proc]

        result = self.tool.execute(app_name="WhatsApp Desktop")

        assert result.success is True
        mock_startfile.assert_called_once_with(
            r"shell:AppsFolder\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"
        )
        assert result.output["tool"] == "open_application"
        assert result.output["application"] == "whatsapp"
        assert result.output["launch_type"] == ApplicationType.PACKAGED_APP
        assert result.output["pid"] == 24680
        assert result.output["message"] == "WhatsApp launched successfully."

    @patch("os.startfile", side_effect=OSError("Windows Shell error"))
    def test_whatsapp_packaged_launch_failure(self, mock_startfile):
        """Failure during packaged application launch returns structured failure result."""
        result = self.tool.execute(app_name="whatsapp")

        assert result.success is False
        assert result.output["tool"] == "open_application"
        assert result.output["application"] == "whatsapp"
        assert result.output["launch_type"] == ApplicationType.PACKAGED_APP
        assert "Windows Shell error" in result.output["error"]

    def test_dynamic_system_application_resolution(self):
        """Dynamic discovery finds installed applications present on system (e.g. AnyDesk, Android Studio)."""
        for cand in ["anydesk", "android studio", "visual studio installer"]:
            res = self.tool.resolve_application(cand)
            if res is not None:
                target, display_name, launch_type = res
                assert len(target) > 0
                assert len(display_name) > 0
                assert launch_type == ApplicationType.WIN32
                break


if __name__ == "__main__":
    unittest.main()
