"""Unit tests for Text-to-Speech (TTS) providers.
"""

from unittest.mock import MagicMock, patch
import pytest

from voice.tts import DisabledTTSProvider, WindowsSapiTTSProvider, TTSProvider


def test_disabled_tts_provider():
    provider = DisabledTTSProvider()
    assert provider.initialize() is True
    assert provider.speak("Hello world") is True
    provider.stop()  # Should not raise
    provider.shutdown()  # Should not raise


def test_windows_sapi_tts_empty_text():
    provider = WindowsSapiTTSProvider()
    # Empty or whitespace text should return True without calling COM
    assert provider.speak("") is True
    assert provider.speak("   ") is True


@patch("voice.tts.win32com")
@patch("voice.tts.pythoncom")
def test_windows_sapi_tts_mocked_flow(mock_pythoncom, mock_win32com):
    mock_spvoice = MagicMock()
    mock_win32com.client.Dispatch.return_value = mock_spvoice

    with patch("voice.tts.settings.TTS_ENABLED", True):
        provider = WindowsSapiTTSProvider(rate=0, volume=80)
        assert provider.initialize() is True
        mock_win32com.client.Dispatch.assert_called_with("SAPI.SpVoice")
        assert mock_spvoice.Rate == 0
        assert mock_spvoice.Volume == 80

        success = provider.speak("Testing Jarvis speech synthesis")
        assert success is True
        mock_spvoice.Speak.assert_called_with("Testing Jarvis speech synthesis", 0)

        provider.stop()
        mock_spvoice.Speak.assert_called_with("", 2)

        provider.shutdown()
        assert provider._speaker is None


@patch("voice.tts.win32com", None)
def test_windows_sapi_missing_dependency():
    provider = WindowsSapiTTSProvider()
    with patch("voice.tts.settings.TTS_ENABLED", True):
        assert provider.initialize() is False
