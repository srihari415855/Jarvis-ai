"""Unit tests for Phase 3 Computer Perception and local Windows OCR.
"""

import os
from unittest.mock import MagicMock, patch
import pytest

from tools.computer.perception import ComputerPerception, ComputerPerceptionTool
from tools.base import RiskLevel


def test_computer_perception_tool_schema():
    tool = ComputerPerceptionTool()
    assert tool.name == "observe_screen"
    assert tool.risk_level == RiskLevel.LOW
    schema = tool.to_schema()
    assert "parameters" in schema
    assert "include_ocr" in schema["parameters"]["properties"]


@patch("tools.computer.perception.ctypes.windll.user32.GetForegroundWindow")
@patch("tools.computer.perception.ctypes.windll.user32.GetWindowTextW")
@patch("tools.computer.perception.ctypes.windll.user32.GetWindowThreadProcessId")
@patch("tools.computer.perception.psutil.Process")
def test_active_window_detection_mocked(mock_proc_cls, mock_get_pid, mock_get_text, mock_get_fg):
    mock_get_fg.return_value = 12345
    def fake_get_text(hwnd, buff, length):
        buff.value = "Google - Google Chrome"
    mock_get_text.side_effect = fake_get_text

    def fake_get_pid(hwnd, byref_pid):
        byref_pid._obj.value = 9999
    mock_get_pid.side_effect = fake_get_pid

    mock_proc = MagicMock()
    mock_proc.name.return_value = "chrome.exe"
    mock_proc_cls.return_value = mock_proc

    perception = ComputerPerception()
    info = perception.get_active_window()

    assert info["hwnd"] == 12345
    assert info["title"] == "Google - Google Chrome"
    assert info["application"] == "chrome.exe"


def test_ephemeral_screenshot_cleanup():
    perception = ComputerPerception()
    with patch("PIL.ImageGrab.grab") as mock_grab:
        mock_img = MagicMock()
        mock_grab.return_value = mock_img

        shot_path = perception.capture_screenshot(ephemeral=True)
        assert shot_path is not None
        assert os.path.exists(shot_path)

        perception.cleanup_ephemeral_screenshots()
        assert not os.path.exists(shot_path)


def test_perception_observe_and_tool_execution():
    perception = ComputerPerception()
    perception.get_active_window = MagicMock(return_value={
        "hwnd": 999,
        "title": "Calculator",
        "application": "CalculatorApp.exe",
        "pid": 555,
    })
    perception.inspect_ui_tree = MagicMock(return_value=[
        {"name": "One", "control_type": "Button", "enabled": True, "visible": True}
    ])

    tool = ComputerPerceptionTool(perception=perception)
    res = tool.execute(include_elements=True)

    assert res.success is True
    assert res.output["application"] == "CalculatorApp.exe"
    assert res.output["active_window"] == "Calculator"
    assert res.output["elements_count"] == 1


@patch("os.path.exists", return_value=True)
@patch("winocr.recognize_pil_sync")
def test_perform_ocr_mocked(mock_winocr, mock_exists):
    mock_winocr.return_value = {
        "text": "File Edit View Help",
        "lines": [{"text": "File Edit View Help"}],
    }

    perception = ComputerPerception()
    perception.capture_screenshot = MagicMock(return_value=None)

    with patch("PIL.Image.open") as mock_open:
        mock_img = MagicMock()
        mock_open.return_value = mock_img

        res = perception.perform_ocr(image_path="dummy_path.png")
        assert res["available"] is True
        assert res["text"] == "File Edit View Help"
        assert res["lines_count"] == 1


@patch("winocr.recognize_pil_sync")
def test_observe_fallback_to_ocr_when_ui_tree_empty(mock_winocr):
    mock_winocr.return_value = {
        "text": "DirectX Game Title",
        "lines": [{"text": "DirectX Game Title"}],
    }

    perception = ComputerPerception()
    perception.get_active_window = MagicMock(return_value={
        "hwnd": 111,
        "title": "Canvas Window",
        "application": "game.exe",
        "pid": 222,
    })
    perception.inspect_ui_tree = MagicMock(return_value=[])  # Empty UI tree
    perception.perform_ocr = MagicMock(return_value={
        "text": "DirectX Game Title",
        "lines": ["DirectX Game Title"],
        "available": True,
    })

    obs = perception.observe(include_elements=True)
    assert obs["elements_count"] == 0
    assert "ocr_text" in obs
    assert obs["ocr_text"] == "DirectX Game Title"
