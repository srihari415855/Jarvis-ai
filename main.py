"""JARVIS Day 1 Foundation - CLI Interface
"""

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
from core.permissions import PermissionManager
from core.agent import JarvisAgent
from security.audit import audit_logger

# Configure logging according to LOG_LEVEL
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def print_banner():
    print("=" * 40)
    print("              J A R V I S               ")
    print(f"          Local AI Agent v{settings.JARVIS_VERSION}         ")
    print("=" * 40)


def build_agent() -> tuple[JarvisAgent, OllamaClient, ToolRegistry, PermissionManager]:
    """Assemble and configure all Day-1 agent subsystems."""
    client = OllamaClient(
        base_url=settings.OLLAMA_BASE_URL,
        default_model=settings.OLLAMA_MODEL,
    )

    registry = ToolRegistry()
    registry.register(GetSystemInfoTool())
    registry.register(ListAllowedApplicationsTool())
    registry.register(OpenApplicationTool())

    permission_manager = PermissionManager()
    executor = ToolExecutor(registry=registry, permission_manager=permission_manager)

    agent = JarvisAgent(
        client=client,
        registry=registry,
        executor=executor,
        model=settings.OLLAMA_MODEL,
    )
    return agent, client, registry, permission_manager


def main():
    print_banner()
    audit_logger.log_event("STARTUP", {"version": settings.JARVIS_VERSION})

    agent, client, registry, permission_manager = build_agent()

    if client.is_available():
        models = client.list_models()
        active_model = settings.OLLAMA_MODEL or (models[0] if models else "None")
        print(f"Jarvis online. Connected to model: {active_model}\n")
    else:
        print("Jarvis online.")
        print(f"[!] Warning: Ollama daemon is offline at {client.base_url}.")
        print("    Run `ollama serve` to enable local model inference.\n")

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
        elif cmd_lower in ("help", "/help"):
            print("\nAvailable Commands:")
            print("  help    - Show this help message")
            print("  status  - Show system and model status")
            print("  tools   - List available safe tools")
            print("  audit   - View recent security audit events")
            print("  clear   - Clear conversation context")
            print("  exit    - Exit JARVIS\n")
            continue
        elif cmd_lower in ("status", "/status"):
            online = client.is_available()
            print(f"\nStatus:")
            print(f"  Ollama: {'ONLINE' if online else 'OFFLINE'} ({client.base_url})")
            print(f"  Model: {agent.model or 'Not configured'}")
            print(f"  Registered Tools: {len(registry.list_tools())}")
            print(f"  Context History: {len(agent.history)} messages\n")
            continue
        elif cmd_lower in ("tools", "/tools"):
            print("\nRegistered Safe Tools:")
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


if __name__ == "__main__":
    main()
