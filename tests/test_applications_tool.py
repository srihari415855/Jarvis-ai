"""Unit tests for OpenApplicationTool.
"""

import unittest
from unittest.mock import MagicMock, patch
from tools.computer.applications import OpenApplicationTool


class TestOpenApplicationTool(unittest.TestCase):

    def setUp(self):
        self.tool = OpenApplicationTool()

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

    def test_unknown_app_rejected(self):
        result = self.tool.execute(app_name="unknown_nonexistent_binary_xyz")
        assert not result.success
        assert "could not be found" in result.error


if __name__ == "__main__":
    unittest.main()
