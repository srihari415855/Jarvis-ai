"""Configuration settings for JARVIS.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


class Settings:
    """Application settings loaded from environment variables with safe defaults."""

    JARVIS_NAME: str = os.getenv("JARVIS_NAME", "Jarvis")
    JARVIS_VERSION: str = os.getenv("JARVIS_VERSION", "0.3.0")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Voice / Speech Settings
    VOICE_ENABLED: bool = os.getenv("VOICE_ENABLED", "true").lower() in ("true", "1", "yes")
    STT_MODEL: str = os.getenv("STT_MODEL", "base")
    STT_DEVICE: str = os.getenv("STT_DEVICE", "auto")
    STT_COMPUTE_TYPE: str = os.getenv("STT_COMPUTE_TYPE", "auto")
    TTS_ENABLED: bool = os.getenv("TTS_ENABLED", "true").lower() in ("true", "1", "yes")
    VOICE_LANGUAGE: str = os.getenv("VOICE_LANGUAGE", "en")
    VOICE_HOTKEY: str = os.getenv("VOICE_HOTKEY", "F9")
    VOICE_LOG_LEVEL: str = os.getenv("VOICE_LOG_LEVEL", "INFO").upper()

    # Paths
    BASE_DIR: Path = BASE_DIR
    LOGS_DIR: Path = BASE_DIR / "logs"

    @classmethod
    def get_summary(cls) -> dict:
        return {
            "name": cls.JARVIS_NAME,
            "version": cls.JARVIS_VERSION,
            "ollama_base_url": cls.OLLAMA_BASE_URL,
            "ollama_model": cls.OLLAMA_MODEL,
            "log_level": cls.LOG_LEVEL,
            "voice_enabled": cls.VOICE_ENABLED,
            "stt_model": cls.STT_MODEL,
            "stt_device": cls.STT_DEVICE,
            "tts_enabled": cls.TTS_ENABLED,
            "voice_language": cls.VOICE_LANGUAGE,
        }


settings = Settings()
