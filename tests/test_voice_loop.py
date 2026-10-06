"""Unit tests for VoiceLoop and text cleaning.
"""

from unittest.mock import MagicMock
import numpy as np
import pytest

from voice.voice_loop import VoiceLoop, clean_text_for_speech


def test_clean_text_for_speech():
    assert clean_text_for_speech("") == ""
    assert clean_text_for_speech("   ") == ""

    markdown_sample = (
        "### System Status\n"
        "Here is the list:\n"
        "* Item 1\n"
        "- Item 2\n"
        "Please check `config.py` and the following:\n"
        "```python\n"
        "def foo():\n"
        "    return 42\n"
        "```\n"
        "Thank you **very** much!"
    )

    cleaned = clean_text_for_speech(markdown_sample)
    assert "```" not in cleaned
    assert "def foo():" not in cleaned
    assert "Code output omitted." in cleaned
    assert "config.py" in cleaned  # Inline code preserved without backticks
    assert "###" not in cleaned
    assert "**" not in cleaned
    assert "very" in cleaned


def test_voice_loop_no_audio():
    mock_mic = MagicMock()
    mock_mic.record_fixed_duration.return_value = None
    mock_stt = MagicMock()
    mock_agent = MagicMock()
    mock_tts = MagicMock()

    loop = VoiceLoop(microphone=mock_mic, stt=mock_stt, agent=mock_agent, tts=mock_tts)
    metrics = loop.process_voice_turn(duration_seconds=1.0)
    assert metrics is None
    mock_stt.transcribe.assert_not_called()
    mock_agent.process_input.assert_not_called()
    mock_tts.speak.assert_not_called()


def test_voice_loop_empty_transcription():
    mock_mic = MagicMock()
    mock_mic.record_fixed_duration.return_value = np.zeros(16000, dtype=np.float32)
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = ""
    mock_agent = MagicMock()
    mock_tts = MagicMock()

    loop = VoiceLoop(microphone=mock_mic, stt=mock_stt, agent=mock_agent, tts=mock_tts)
    metrics = loop.process_voice_turn(duration_seconds=1.0)
    assert metrics is None
    mock_agent.process_input.assert_not_called()
    mock_tts.speak.assert_not_called()


def test_voice_loop_successful_cycle():
    mock_mic = MagicMock()
    mock_mic.record_fixed_duration.return_value = np.zeros(16000, dtype=np.float32)
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = "What time is it?"
    mock_agent = MagicMock()
    mock_agent.process_input.return_value = "It is 3 PM."
    mock_tts = MagicMock()
    mock_tts.speak.return_value = True

    loop = VoiceLoop(microphone=mock_mic, stt=mock_stt, agent=mock_agent, tts=mock_tts)
    metrics = loop.process_voice_turn(duration_seconds=1.0)

    assert metrics is not None
    assert metrics["user_text"] == "What time is it?"
    assert metrics["response_text"] == "It is 3 PM."
    assert "total_latency" in metrics
    assert "capture_time" in metrics
    assert "stt_time" in metrics
    assert "agent_time" in metrics
    assert "tts_time" in metrics

    mock_mic.record_fixed_duration.assert_called_once_with(duration_seconds=1.0)
    mock_stt.transcribe.assert_called_once()
    mock_agent.process_input.assert_called_once_with("What time is it?")
    mock_tts.speak.assert_called_once_with("It is 3 PM.")
