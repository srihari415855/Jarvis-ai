"""JARVIS - Local AI Agent (CLI and Voice Assistant)
"""

import argparse
import sys
import logging

from config.settings import settings
from models.ollama_client import OllamaClient
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from tools.computer.applications import (
    GetSystemInfoTool,
    ListAllowedApplicationsTool,
    OpenApplicationTool,
)
from tools.browser.browser import BrowserTool
from tools.filesystem.filesystem import ListDirectoryTool, ReadFileTool
from core.permissions import PermissionManager
from core.agent import JarvisAgent
from security.audit import audit_logger

from voice.microphone import MicrophoneManager
from voice.stt import WhisperSTTProvider
from voice.tts import WindowsSapiTTSProvider, DisabledTTSProvider
from voice.voice_loop import VoiceLoop

# Configure logging according to LOG_LEVEL
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def print_banner():
    print("=" * 45)
    print("                 J A R V I S                 ")
    print(f"        Local AI Voice Assistant v{settings.JARVIS_VERSION}       ")
    print("=" * 45)


def build_system() -> tuple[JarvisAgent, OllamaClient, ToolRegistry, PermissionManager, VoiceLoop]:
    """Assemble all core agent and voice subsystems."""
    client = OllamaClient(
        base_url=settings.OLLAMA_BASE_URL,
        default_model=settings.OLLAMA_MODEL,
    )

    registry = ToolRegistry()
    registry.register(GetSystemInfoTool())
    registry.register(ListAllowedApplicationsTool())
    registry.register(OpenApplicationTool())
    registry.register(BrowserTool())
    registry.register(ListDirectoryTool())
    registry.register(ReadFileTool())

    permission_manager = PermissionManager()
    executor = ToolExecutor(registry=registry, permission_manager=permission_manager)

    agent = JarvisAgent(
        client=client,
        registry=registry,
        executor=executor,
        model=settings.OLLAMA_MODEL,
    )

    # Initialize Voice Subsystems
    mic = MicrophoneManager()
    stt = WhisperSTTProvider()
    tts = WindowsSapiTTSProvider() if settings.TTS_ENABLED else DisabledTTSProvider()
    voice_loop = VoiceLoop(microphone=mic, stt=stt, agent=agent, tts=tts)

    return agent, client, registry, permission_manager, voice_loop


def run_cli_loop(agent: JarvisAgent, client: OllamaClient, registry: ToolRegistry, permission_manager: PermissionManager, voice_loop: VoiceLoop):
    """Run interactive text CLI loop."""
    print("Mode: CLI (type 'voice' to switch to Voice Mode, 'help' for commands)\n")

    while True:
        try:
            user_input = input("You > ").strip()
        except KeyboardInterrupt:
            print("\nInterrupt received. Use 'exit' to quit or enter a prompt.")
            continue
        except EOFError:
            print("\nSession ended. Exiting Jarvis.")
            audit_logger.log_event("SHUTDOWN", {"reason": "EOF"})
            break

        if not user_input:
            continue

        cmd_lower = user_input.lower()
        if cmd_lower in ("exit", "quit", "/exit", "/quit"):
            print("Jarvis shutting down. Goodbye!")
            audit_logger.log_event("SHUTDOWN", {"reason": "user_command"})
            break
        elif cmd_lower in ("voice", "/voice"):
            if not settings.VOICE_ENABLED:
                print("Voice mode is disabled in .env configuration.\n")
                continue
            if not voice_loop.microphone.is_available():
                print("Cannot start voice mode: No microphone detected on system.\n")
                continue
            voice_loop.run_interactive_loop()
            print("Mode: CLI\n")
            continue
        elif cmd_lower in ("help", "/help"):
            print("\nAvailable Commands:")
            print("  help    - Show this help message")
            print("  voice   - Switch to Push-to-Talk Voice Mode")
            print("  status  - Show system, model, and voice status")
            print("  tools   - List available safe tools")
            print("  audit   - View recent security audit events")
            print("  clear   - Clear conversation context")
            print("  exit    - Exit JARVIS\n")
            continue
        elif cmd_lower in ("status", "/status"):
            online = client.is_available()
            mic_avail = voice_loop.microphone.is_available()
            print(f"\nStatus:")
            print(f"  Ollama: {'ONLINE' if online else 'OFFLINE'} ({client.base_url})")
            print(f"  Model: {agent.model or 'Not configured'}")
            print(f"  Microphone: {'DETECTED' if mic_avail else 'UNAVAILABLE'}")
            print(f"  STT Model: {settings.STT_MODEL} (faster-whisper)")
            print(f"  TTS Engine: {'Windows SAPI' if settings.TTS_ENABLED else 'Disabled'}")
            print(f"  Registered Tools: {len(registry.list_tools())}")
            print(f"  Context History: {len(agent.history)} messages\n")
            continue
        elif cmd_lower in ("tools", "/tools"):
            print("\nRegistered Tools:")
            for tool in registry.list_tools():
                print(f"  - {tool.name} (Risk: {tool.risk_level.value}): {tool.description}")
            print()
            continue
        elif cmd_lower in ("audit", "/audit"):
            print("\nRecent Security Audit Events:")
            events = audit_logger.get_recent_events(limit=10)
            if not events:
                print("  No audit events recorded yet.")
            for e in events:
                print(f"  [{e['timestamp']}] {e['event_type']}: {e['details']}")
            print()
            continue
        elif cmd_lower in ("clear", "/clear"):
            agent.reset_context()
            print("Conversation history cleared.\n")
            continue

        try:
            response = agent.process_input(user_input)
            print(f"\nJarvis > {response}\n")
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
        except Exception as exc:
            print(f"\nJarvis > An error occurred: {exc}\n")


def main():
    parser = argparse.ArgumentParser(description="JARVIS Personal AI Assistant")
    parser.add_argument(
        "--mode",
        choices=["cli", "voice"],
        default="cli",
        help="Interaction mode: 'cli' (default) or 'voice'",
    )
    args = parser.parse_args()

    print_banner()
    audit_logger.log_event("STARTUP", {"version": settings.JARVIS_VERSION, "mode": args.mode})

    agent, client, registry, permission_manager, voice_loop = build_system()

    if client.is_available():
        models = client.list_models()
        active_model = settings.OLLAMA_MODEL or (models[0] if models else "None")
        print(f"Jarvis online. Connected to model: {active_model}\n")
    else:
        print("Jarvis online.")
        print(f"[!] Warning: Ollama daemon is offline at {client.base_url}.")
        print("    Run `ollama serve` to enable local model inference.\n")

    if args.mode == "voice":
        if not settings.VOICE_ENABLED:
            print("[!] Voice mode is disabled in settings. Falling back to CLI mode.\n")
            run_cli_loop(agent, client, registry, permission_manager, voice_loop)
        elif not voice_loop.microphone.is_available():
            print("[!] No microphone detected. Falling back to CLI mode.\n")
            run_cli_loop(agent, client, registry, permission_manager, voice_loop)
        else:
            voice_loop.run_interactive_loop()
    else:
        run_cli_loop(agent, client, registry, permission_manager, voice_loop)


if __name__ == "__main__":
    main()
