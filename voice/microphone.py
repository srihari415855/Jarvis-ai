"""Microphone input management and audio buffer capture for JARVIS.

Captures audio directly in-memory as float32 NumPy arrays (16 kHz mono)
without creating temporary or persistent audio files on disk.
"""

import logging
import threading
from typing import Any, Dict, List, Optional
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    sd = None

from security.audit import audit_logger

logger = logging.getLogger("jarvis.voice.microphone")


class MicrophoneManager:
    """Manages audio device detection and push-to-talk audio recording."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        device_index: Optional[int] = None,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index
        self._recording = False
        self._audio_frames: List[np.ndarray] = []
        self._stream: Optional[Any] = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        """Check if any microphone input device is available."""
        if not sd:
            return False
        try:
            devices = sd.query_devices()
            input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
            return len(input_devices) > 0
        except Exception as exc:
            logger.warning(f"Error checking microphone devices: {exc}")
            return False

    def list_input_devices(self) -> List[Dict[str, Any]]:
        """List all available microphone input devices."""
        if not sd:
            return []
        try:
            devices = sd.query_devices()
            return [
                {
                    "index": i,
                    "name": d["name"],
                    "channels": d["max_input_channels"],
                    "default_samplerate": d["default_samplerate"],
                }
                for i, d in enumerate(devices)
                if d.get("max_input_channels", 0) > 0
            ]
        except Exception as exc:
            logger.error(f"Failed to query audio input devices: {exc}")
            return []

    def start_recording(self) -> bool:
        """Start capturing audio into in-memory buffer."""
        if not sd:
            logger.error("sounddevice library is not available.")
            return False

        if not self.is_available():
            logger.error("No microphone input device detected.")
            return False

        with self._lock:
            if self._recording:
                return True

            self._audio_frames.clear()
            self._recording = True

            def _audio_callback(indata, frames, time_info, status):
                if status:
                    logger.debug(f"Audio stream status: {status}")
                if self._recording:
                    self._audio_frames.append(indata.copy())

            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype="float32",
                    device=self.device_index,
                    callback=_audio_callback,
                )
                self._stream.start()
                audit_logger.log_event("VOICE_RECORDING_START", {"samplerate": self.sample_rate})
                return True
            except Exception as exc:
                self._recording = False
                logger.error(f"Failed to start audio stream: {exc}")
                return False

    def stop_recording(self) -> Optional[np.ndarray]:
        """Stop capturing and return the recorded float32 NumPy array."""
        with self._lock:
            if not self._recording:
                return None

            self._recording = False
            try:
                if self._stream:
                    self._stream.stop()
                    self._stream.close()
                    self._stream = None
            except Exception as exc:
                logger.warning(f"Error stopping audio stream: {exc}")

            if not self._audio_frames:
                logger.info("Recording stopped with no audio frames captured.")
                return None

            # Concatenate all in-memory frames into a single 1D float32 array
            audio_data = np.concatenate(self._audio_frames, axis=0)
            if audio_data.ndim > 1:
                audio_data = audio_data.flatten()

            duration_s = round(len(audio_data) / self.sample_rate, 2)
            audit_logger.log_event("VOICE_RECORDING_STOP", {"duration_seconds": duration_s})
            return audio_data

    def record_fixed_duration(self, duration_seconds: float = 3.0) -> Optional[np.ndarray]:
        """Capture audio for a fixed number of seconds synchronously."""
        if not self.start_recording():
            return None
        import time
        time.sleep(duration_seconds)
        return self.stop_recording()
