"""Unit tests for BrowserTool.
"""

from unittest.mock import patch
import pytest

from tools.browser.browser import BrowserTool
from tools.base import RiskLevel


def test_browser_tool_schema():
    tool = BrowserTool()
    assert tool.name == "open_browser"
    assert tool.risk_level == RiskLevel.LOW
    schema = tool.to_schema()
    assert "parameters" in schema
    assert "url" in schema["parameters"]["properties"]


@patch("tools.browser.browser.webbrowser.open")
def test_browser_tool_open_url(mock_open):
    mock_open.return_value = True
    tool = BrowserTool()

    result = tool.execute(url="https://google.com")
    assert result.success is True
    mock_open.assert_called_once_with("https://google.com")
    assert "google.com" in result.output["target_url"]


@patch("tools.browser.browser.webbrowser.open")
def test_browser_tool_search_query(mock_open):
    mock_open.return_value = True
    tool = BrowserTool()

    result = tool.execute(search_query="Python 3.12 documentation")
    assert result.success is True
    mock_open.assert_called_once()
    assert "https://www.google.com/search?q=Python+3.12+documentation" in mock_open.call_args[0][0]


def test_browser_tool_disallow_unsafe_schemes():
    tool = BrowserTool()

    result = tool.execute(url="javascript:alert(1)")
    assert result.success is False
    assert "Invalid or disallowed URL scheme" in result.error

    result2 = tool.execute(url="file:///C:/Windows/System32/cmd.exe")
    assert result2.success is False
    assert "Invalid or disallowed URL scheme" in result2.error


def test_browser_tool_no_args():
    tool = BrowserTool()
    result = tool.execute()
    assert result.success is False
    assert "Either 'url' or 'search_query' must be provided" in result.error
