"""Voice conversation loop coordinating Microphone, STT, JarvisAgent, and TTS.
"""

import logging
import re
import time
from typing import Any, Dict, Optional

from core.agent import JarvisAgent
from security.audit import audit_logger
from voice.microphone import MicrophoneManager
from voice.stt import STTProvider
from voice.tts import TTSProvider

logger = logging.getLogger("jarvis.voice.loop")


def clean_text_for_speech(text: str) -> str:
    """Format raw agent output into natural spoken English.

    Strips markdown syntax, raw code blocks, and technical symbols
    so the TTS engine speaks naturally.
    """
    if not text:
        return ""

    cleaned = text.strip()

    # Remove code blocks ```...```
    cleaned = re.sub(r"```[\s\S]*?```", " Code output omitted. ", cleaned)
    # Remove inline code `...`
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    # Clean list bullets at beginning of lines first
    cleaned = re.sub(r"^\s*[-*•]\s*", "", cleaned, flags=re.MULTILINE)
    # Remove markdown headers
    cleaned = re.sub(r"#+\s*", "", cleaned)
    # Remove bold/italic markdown (**text**, *text*, ***text***)
    cleaned = re.sub(r"\*{1,3}([^\*]+?)\*{1,3}", r"\1", cleaned)
    cleaned = re.sub(r"_{1,3}([^_]+?)_{1,3}", r"\1", cleaned)
    # Remove any leftover lone asterisks
    cleaned = cleaned.replace("*", "")
    # Condense excess whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


class VoiceLoop:
    """Coordinates Microphone -> STT -> JarvisAgent -> TTS pipeline."""

    def __init__(
        self,
        microphone: MicrophoneManager,
        stt: STTProvider,
        agent: JarvisAgent,
        tts: TTSProvider,
    ):
        self.microphone = microphone
        self.stt = stt
        self.agent = agent
        self.tts = tts
        self._running = False

    def process_voice_turn(self, duration_seconds: float = 4.0) -> Optional[Dict[str, Any]]:
        """Execute a single push-to-talk voice interaction turn.

        Returns latency metrics and interaction text.
        """
        turn_start = time.perf_counter()
        metrics: Dict[str, Any] = {}

        # 1. Capture Audio
        print("\n[Voice] Listening... (speak now)")
        capture_start = time.perf_counter()
        audio = self.microphone.record_fixed_duration(duration_seconds=duration_seconds)
        metrics["capture_time"] = round(time.perf_counter() - capture_start, 2)

        if audio is None or len(audio) == 0:
            print("[Voice] No audio captured.")
            return None

        # 2. Local Speech-to-Text
        print("[Voice] Transcribing audio locally...")
        stt_start = time.perf_counter()
        transcribed_text = self.stt.transcribe(audio)
        metrics["stt_time"] = round(time.perf_counter() - stt_start, 2)

        if not transcribed_text:
            print("[Voice] No speech recognized.")
            return None

        print(f"\nYou (Voice) > {transcribed_text}")
        metrics["user_text"] = transcribed_text

        # 3. JarvisAgent Processing (Reasoning, Tools, Permissions)
        agent_start = time.perf_counter()
        response_text = self.agent.process_input(transcribed_text)
        metrics["agent_time"] = round(time.perf_counter() - agent_start, 2)

        print(f"\nJarvis > {response_text}\n")
        metrics["response_text"] = response_text

        # 4. Local Text-to-Speech
        spoken_text = clean_text_for_speech(response_text)
        if spoken_text:
            tts_start = time.perf_counter()
            self.tts.speak(spoken_text)
            metrics["tts_time"] = round(time.perf_counter() - tts_start, 2)

        metrics["total_latency"] = round(time.perf_counter() - turn_start, 2)
        logger.info(
            f"Voice pipeline latency: Total={metrics['total_latency']}s "
            f"(Capture={metrics.get('capture_time')}s, STT={metrics.get('stt_time')}s, "
            f"Agent={metrics.get('agent_time')}s, TTS={metrics.get('tts_time')}s)"
        )
        audit_logger.log_event("VOICE_TURN_COMPLETED", metrics)
        return metrics

    def run_interactive_loop(self) -> None:
        """Run the push-to-talk voice conversation loop."""
        self._running = True
        print("\n" + "=" * 50)
        print("         JARVIS VOICE MODE (Push-to-Talk)        ")
        print("=" * 50)
        print("Controls:")
        print("  [Enter]  - Record speech (4 seconds)")
        print("  'cli'    - Return to text CLI mode")
        print("  'exit'   - Shut down JARVIS")
        print("=" * 50 + "\n")

        # Initialize speech resources
        print("Initializing local speech engine...")
        self.stt.initialize()
        self.tts.initialize()

        while self._running:
            try:
                cmd = input("Press [Enter] to talk, or type 'cli' / 'exit': ").strip().lower()
                if cmd in ("exit", "quit"):
                    print("Exiting voice mode.")
                    self._running = False
                    break
                elif cmd in ("cli", "/cli"):
                    print("Returning to CLI mode.\n")
                    self._running = False
                    break
                elif cmd in ("help", "/help"):
                    print("Voice commands: Press Enter to talk, type 'cli' to return to CLI, 'exit' to quit.\n")
                    continue

                self.process_voice_turn()
            except KeyboardInterrupt:
                print("\nVoice turn interrupted by user.")
                self.tts.stop()
            except Exception as exc:
                print(f"\n[Voice Error]: {exc}\n")
                logger.error(f"Voice loop error: {exc}")
