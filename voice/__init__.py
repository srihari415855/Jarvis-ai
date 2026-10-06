"""Voice package for JARVIS Phase 2 Local Voice Assistant.
"""

from voice.microphone import MicrophoneManager
from voice.stt import STTProvider, WhisperSTTProvider
from voice.tts import TTSProvider, WindowsSapiTTSProvider, DisabledTTSProvider
from voice.voice_loop import VoiceLoop, clean_text_for_speech

__all__ = [
    "MicrophoneManager",
    "STTProvider",
    "WhisperSTTProvider",
    "TTSProvider",
    "WindowsSapiTTSProvider",
    "DisabledTTSProvider",
    "VoiceLoop",
    "clean_text_for_speech",
]
