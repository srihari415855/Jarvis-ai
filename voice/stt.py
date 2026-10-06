"""Speech-to-Text (STT) abstraction and faster-whisper local provider.
"""

from abc import ABC, abstractmethod
import logging
import time
from typing import Any, Optional
import numpy as np

from config.settings import settings
from security.audit import audit_logger

logger = logging.getLogger("jarvis.voice.stt")


class STTProvider(ABC):
    """Abstract base class for speech-to-text providers."""

    @abstractmethod
    def initialize(self) -> bool:
        """Load and initialize model resources."""
        pass

    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe in-memory audio array into text."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Release loaded model resources."""
        pass


class WhisperSTTProvider(STTProvider):
    """Local Speech-to-Text provider backed by faster-whisper."""

    def __init__(
        self,
        model_size: Optional[str] = None,
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        language: Optional[str] = None,
    ):
        self.model_size = model_size or settings.STT_MODEL
        self.device = device or settings.STT_DEVICE
        self.compute_type = compute_type or settings.STT_COMPUTE_TYPE
        self.language = language or settings.VOICE_LANGUAGE
        self._model: Optional[Any] = None

    def initialize(self) -> bool:
        """Load the faster-whisper model locally."""
        if self._model is not None:
            return True

        start_t = time.perf_counter()
        logger.info(f"Loading faster-whisper model '{self.model_size}' (device={self.device}, compute={self.compute_type})...")

        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                model_size_or_path=self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            load_time = round(time.perf_counter() - start_t, 2)
            logger.info(f"faster-whisper model '{self.model_size}' initialized in {load_time}s.")
            audit_logger.log_event("STT_INITIALIZED", {
                "model": self.model_size,
                "device": self.device,
                "load_time_seconds": load_time,
            })
            return True
        except Exception as exc:
            logger.error(f"Failed to initialize faster-whisper model: {exc}")
            self._model = None
            return False

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe in-memory float32 audio array."""
        if audio is None or len(audio) == 0:
            return ""

        # Check silence or near-zero amplitude
        max_amp = float(np.max(np.abs(audio)))
        if max_amp < 0.01:
            logger.debug("Audio buffer is silent; skipping transcription.")
            return ""

        if self._model is None:
            if not self.initialize():
                return ""

        start_t = time.perf_counter()
        try:
            # transcribe takes float32 16kHz mono audio directly
            segments, info = self._model.transcribe(
                audio,
                language=self.language,
                beam_size=5,
                vad_filter=True,
            )

            # Collect transcribed text segments
            text_parts = [seg.text.strip() for seg in segments if seg.text.strip()]
            full_text = " ".join(text_parts).strip()

            duration = round(time.perf_counter() - start_t, 2)
            audit_logger.log_event("STT_TRANSCRIBED", {
                "duration_seconds": duration,
                "characters": len(full_text),
            })
            logger.info(f"Transcribed in {duration}s: '{full_text}'")
            return full_text
        except Exception as exc:
            logger.error(f"Error during transcription: {exc}")
            return ""

    def shutdown(self) -> None:
        """Unload model from memory."""
        self._model = None
        logger.info("faster-whisper model unloaded.")
