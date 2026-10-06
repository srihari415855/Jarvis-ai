"""Registry for discovering and managing JARVIS tools.
"""

from typing import Dict, List, Optional
from tools.base import BaseTool


class ToolRegistry:
    """Manages tool registration, discovery, and schema generation."""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        if not tool.name:
            raise ValueError("Tool name must not be empty.")
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Retrieve a registered tool by its unique name."""
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_schemas(self) -> List[dict]:
        """Return tool definitions formatted for LLM system prompt / tool calling."""
        return [tool.to_schema() for tool in self._tools.values()]
