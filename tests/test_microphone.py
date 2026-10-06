"""Unit tests for MicrophoneManager audio capture.
"""

from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from voice.microphone import MicrophoneManager


def test_microphone_init():
    mic = MicrophoneManager(sample_rate=16000, channels=1, device_index=0)
    assert mic.sample_rate == 16000
    assert mic.channels == 1
    assert mic.device_index == 0
    assert not mic._recording


@patch("voice.microphone.sd")
def test_microphone_is_available(mock_sd):
    mock_sd.query_devices.return_value = [
        {"name": "Speakers", "max_input_channels": 0},
        {"name": "Microphone Array", "max_input_channels": 2, "default_samplerate": 48000},
    ]
    mic = MicrophoneManager()
    assert mic.is_available() is True

    devices = mic.list_input_devices()
    assert len(devices) == 1
    assert devices[0]["name"] == "Microphone Array"


@patch("voice.microphone.sd", None)
def test_microphone_when_sd_missing():
    mic = MicrophoneManager()
    assert mic.is_available() is False
    assert mic.list_input_devices() == []
    assert mic.start_recording() is False
    assert mic.stop_recording() is None


@patch("voice.microphone.sd")
def test_microphone_recording_and_stopping(mock_sd):
    mock_sd.query_devices.return_value = [
        {"name": "Mic", "max_input_channels": 1, "default_samplerate": 16000}
    ]
    mock_stream = MagicMock()
    mock_sd.InputStream.return_value = mock_stream

    mic = MicrophoneManager()
    started = mic.start_recording()
    assert started is True
    assert mic._recording is True

    # Simulate callback frames
    frame1 = np.ones((1600, 1), dtype=np.float32) * 0.1
    frame2 = np.ones((1600, 1), dtype=np.float32) * 0.2
    mic._audio_frames.append(frame1)
    mic._audio_frames.append(frame2)

    audio = mic.stop_recording()
    assert audio is not None
    assert isinstance(audio, np.ndarray)
    assert len(audio) == 3200
    assert audio.ndim == 1
    assert not mic._recording
