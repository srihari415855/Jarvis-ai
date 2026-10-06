"""Unit tests for Phase 3 Computer GUI Control.
"""

from unittest.mock import MagicMock, patch
import pytest

from tools.computer.control import (
    ComputerControl,
    ComputerControlTool,
    UIControlTarget,
)
from tools.base import RiskLevel


def test_computer_control_tool_schema():
    tool = ComputerControlTool()
    assert tool.name == "computer_control"
    assert tool.risk_level == RiskLevel.MEDIUM
    schema = tool.to_schema()
    assert "parameters" in schema
    assert "action" in schema["parameters"]["properties"]


@patch("pywinauto.Desktop")
def test_focus_window_mocked(mock_desktop_cls):
    mock_desktop = MagicMock()
    mock_win = MagicMock()
    mock_win.window_text.return_value = "Notepad"
    mock_desktop.windows.return_value = [mock_win]
    mock_desktop_cls.return_value = mock_desktop

    control = ComputerControl()
    res = control.focus_window("Notepad")

    assert res["action"] == "focus_window"
    assert res["status"] == "focused"
    mock_win.set_focus.assert_called_once()


@patch("pywinauto.Desktop")
def test_click_element_mocked(mock_desktop_cls):
    mock_desktop = MagicMock()
    mock_win = MagicMock()
    mock_elem = MagicMock()
    mock_elem.exists.return_value = True
    mock_win.child_window.return_value = mock_elem
    mock_desktop.top_window.return_value = mock_win
    mock_desktop_cls.return_value = mock_desktop

    control = ComputerControl()
    target = UIControlTarget(name="Close", control_type="Button")
    res = control.click_element(target)

    assert res["action"] == "click_element"
    mock_elem.click_input.assert_called_once()


@patch("pywinauto.keyboard.send_keys")
def test_type_text_mocked(mock_send_keys):
    control = ComputerControl()
    res = control.type_text("Hello World")

    assert res["action"] == "type_text"
    assert res["chars_typed"] == 11
    mock_send_keys.assert_called_once_with("Hello World", with_spaces=True)


@patch("pywinauto.keyboard.send_keys")
def test_press_key_mocked(mock_send_keys):
    control = ComputerControl()
    res = control.press_key("enter")

    assert res["action"] == "press_key"
    mock_send_keys.assert_called_once_with("{ENTER}")


@patch("pywinauto.keyboard.send_keys")
def test_hotkey_mocked(mock_send_keys):
    control = ComputerControl()
    res = control.hotkey(["ctrl", "c"])

    assert res["action"] == "hotkey"
    mock_send_keys.assert_called_once_with("^{C}")


def test_forbidden_hotkeys_rejected():
    control = ComputerControl()
    with pytest.raises(ValueError, match="forbidden by security policy"):
        control.hotkey(["alt", "f4"])

    with pytest.raises(ValueError, match="forbidden by security policy"):
        control.hotkey(["ctrl", "alt", "del"])


def test_computer_control_tool_execution_mocked():
    mock_control = MagicMock()
    mock_control.focus_window.return_value = {"action": "focus_window", "status": "focused"}
    tool = ComputerControlTool(control=mock_control)

    res = tool.execute(action="focus_window", window_title="Notepad")
    assert res.success is True
    mock_control.focus_window.assert_called_once_with("Notepad")
