"""Unit tests for Speech-to-Text provider abstraction.
"""

from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from voice.stt import WhisperSTTProvider


def test_stt_provider_configuration():
    """Verify STT configuration initializes with custom parameters."""
    provider = WhisperSTTProvider(
        model_size="tiny",
        device="cpu",
        compute_type="int8",
        language="en",
    )
    assert provider.model_size == "tiny"
    assert provider.device == "cpu"
    assert provider.compute_type == "int8"
    assert provider.language == "en"
    assert provider._model is None


@patch("faster_whisper.WhisperModel")
def test_stt_provider_initialization(mock_whisper_class):
    """Verify STT model loads and handles initialization properly."""
    mock_instance = MagicMock()
    mock_whisper_class.return_value = mock_instance

    provider = WhisperSTTProvider(model_size="tiny", device="cpu")
    success = provider.initialize()

    assert success is True
    assert provider._model is not None
    mock_whisper_class.assert_called_once_with(
        model_size_or_path="tiny",
        device="cpu",
        compute_type="auto",
    )


def test_empty_audio_handling():
    """Verify empty or silent audio returns empty string without errors."""
    provider = WhisperSTTProvider(model_size="tiny")

    # None audio
    assert provider.transcribe(None) == ""

    # Zero length audio
    assert provider.transcribe(np.array([], dtype=np.float32)) == ""

    # Silent audio (near-zero amplitude)
    silence = np.zeros(16000, dtype=np.float32)
    assert provider.transcribe(silence) == ""


@patch("faster_whisper.WhisperModel")
def test_transcribe_audio_success(mock_whisper_class):
    """Verify valid audio array transcription."""
    mock_instance = MagicMock()
    # Mock segment
    mock_seg = MagicMock()
    mock_seg.text = "hello jarvis"
    mock_instance.transcribe.return_value = ([mock_seg], MagicMock())
    mock_whisper_class.return_value = mock_instance

    provider = WhisperSTTProvider(model_size="tiny")
    provider.initialize()

    # Generate test audio with amplitude > 0.01
    audio = np.sin(np.linspace(0, 100, 16000)).astype(np.float32)
    result = provider.transcribe(audio)

    assert result == "hello jarvis"
    mock_instance.transcribe.assert_called_once()
