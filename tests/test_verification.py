"""Unit tests for ActionVerifier and empirical verification.
"""

from unittest.mock import MagicMock
import pytest

from tools.computer.verification import ActionVerifier, VerificationResult


def test_verify_browser_navigation_success():
    mock_manager = MagicMock()
    mock_manager.is_active = True
    mock_page = MagicMock()
    mock_page.url = "https://github.com/torvalds/linux"
    mock_page.title.return_value = "torvalds/linux: Linux kernel source tree"
    mock_manager._page = mock_page

    verifier = ActionVerifier()
    res = verifier.verify_browser_navigation(
        mock_manager,
        expected_url_pattern=r"github\.com",
        expected_title_pattern="Linux kernel",
    )

    assert res.verified is True
    assert "Navigation verified" in res.message


def test_verify_browser_navigation_failure_mismatch():
    mock_manager = MagicMock()
    mock_manager.is_active = True
    mock_page = MagicMock()
    mock_page.url = "https://example.com"
    mock_page.title.return_value = "Example Domain"
    mock_manager._page = mock_page

    verifier = ActionVerifier()
    res = verifier.verify_browser_navigation(
        mock_manager,
        expected_url_pattern=r"github\.com",
    )

    assert res.verified is False
    assert "did not match expected pattern" in res.message


def test_verify_browser_inactive_no_fabrication():
    mock_manager = MagicMock()
    mock_manager.is_active = False

    verifier = ActionVerifier()
    res = verifier.verify_browser_navigation(mock_manager)

    assert res.verified is False
    assert "closed or inactive" in res.message


def test_verify_browser_search_results_success():
    mock_manager = MagicMock()
    mock_manager.is_active = True
    mock_page = MagicMock()
    mock_page.url = "https://www.google.com/search?q=Python+tutorials"
    mock_page.title.return_value = "Python tutorials - Google Search"

    mock_headings = MagicMock()
    mock_headings.all_inner_texts.return_value = [
        "Python For Beginners | Python.org",
        "Python Tutorial - W3Schools",
        "Learn Python Programming",
    ]
    mock_page.locator.return_value = mock_headings
    mock_page.inner_text.return_value = "Python tutorials for beginners, data science, and web development."
    mock_manager._page = mock_page

    verifier = ActionVerifier()
    res = verifier.verify_browser_search_results(mock_manager, query="Python tutorials")

    assert res.verified is True
    assert "Python tutorials" in res.message
    assert res.actual_observation["result_indicators_found"] == 3


def test_verify_browser_search_results_failure():
    mock_manager = MagicMock()
    mock_manager.is_active = True
    mock_page = MagicMock()
    mock_page.url = "https://www.google.com"
    mock_page.title.return_value = "Google"

    mock_headings = MagicMock()
    mock_headings.all_inner_texts.return_value = []
    mock_page.locator.return_value = mock_headings
    mock_page.inner_text.return_value = "About Store Gmail Images Sign in"
    mock_manager._page = mock_page

    verifier = ActionVerifier()
    res = verifier.verify_browser_search_results(mock_manager, query="Quantum Computing")

    assert res.verified is False
    assert "Could not confirm search results" in res.message


def test_verify_window_active():
    mock_perception = MagicMock()
    mock_perception.get_active_window.return_value = {
        "title": "Untitled - Notepad",
        "application": "notepad.exe",
    }

    verifier = ActionVerifier()
    res = verifier.verify_window_active(mock_perception, "Notepad")
    assert res.verified is True

    res2 = verifier.verify_window_active(mock_perception, "Calculator")
    assert res2.verified is False
