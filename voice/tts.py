"""Text-to-Speech (TTS) abstraction and Windows SAPI local provider.
"""

from abc import ABC, abstractmethod
import logging
import time
from typing import Any, Optional

try:
    import win32com.client
    import pythoncom
except ImportError:
    win32com = None
    pythoncom = None

from config.settings import settings
from security.audit import audit_logger

logger = logging.getLogger("jarvis.voice.tts")


class TTSProvider(ABC):
    """Abstract base class for local Text-to-Speech engines."""

    @abstractmethod
    def initialize(self) -> bool:
        """Initialize TTS resources."""
        pass

    @abstractmethod
    def speak(self, text: str) -> bool:
        """Speak the given text aloud."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Immediately interrupt/stop current speech output."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Release TTS resources."""
        pass


class WindowsSapiTTSProvider(TTSProvider):
    """Local Windows SAPI.SpVoice Text-to-Speech provider (100% offline)."""

    def __init__(self, rate: int = 1, volume: int = 100):
        self.rate = rate          # -10 to +10
        self.volume = volume      # 0 to 100
        self._speaker: Optional[Any] = None

    def initialize(self) -> bool:
        """Initialize the SAPI.SpVoice COM interface."""
        if not settings.TTS_ENABLED:
            logger.info("TTS is disabled in configuration.")
            return False

        if not win32com:
            logger.error("pywin32 / win32com is not available for Windows SAPI TTS.")
            return False

        try:
            if pythoncom:
                pythoncom.CoInitialize()
            self._speaker = win32com.client.Dispatch("SAPI.SpVoice")
            self._speaker.Rate = self.rate
            self._speaker.Volume = self.volume
            logger.info("Windows SAPI TTS initialized successfully.")
            return True
        except Exception as exc:
            logger.error(f"Failed to initialize Windows SAPI TTS: {exc}")
            self._speaker = None
            return False

    def speak(self, text: str) -> bool:
        """Speak text aloud using SAPI.

        Blocks until speech finishes or user interrupts with stop().
        """
        if not settings.TTS_ENABLED:
            return True

        clean_text = text.strip()
        if not clean_text:
            return True

        if self._speaker is None:
            if not self.initialize():
                return False

        start_t = time.perf_counter()
        try:
            audit_logger.log_event("TTS_START", {"characters": len(clean_text)})
            # Flag 0 = Synchronous speech, Flag 2 = Purge before speaking
            # We use synchronous speech so the loop waits for speech to complete
            self._speaker.Speak(clean_text, 0)
            duration = round(time.perf_counter() - start_t, 2)
            audit_logger.log_event("TTS_COMPLETE", {"duration_seconds": duration})
            return True
        except Exception as exc:
            logger.error(f"Error during TTS playback: {exc}")
            return False

    def stop(self) -> None:
        """Interrupt and purge current speech output."""
        if self._speaker is not None:
            try:
                # Flag 2 = SVSFPurgeBeforeSpeak (clears audio buffer immediately)
                self._speaker.Speak("", 2)
                logger.info("Speech playback interrupted.")
            except Exception as exc:
                logger.debug(f"Error stopping speech: {exc}")

    def shutdown(self) -> None:
        """Release COM speaker object."""
        self.stop()
        self._speaker = None


class DisabledTTSProvider(TTSProvider):
    """No-op TTS provider used when speech output is disabled."""

    def initialize(self) -> bool:
        return True

    def speak(self, text: str) -> bool:
        return True

    def stop(self) -> None:
        pass

    def shutdown(self) -> None:
        pass
