"""Base definitions and interfaces for JARVIS tools.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class RiskLevel(str, Enum):
    """Risk classification for tool actions."""
    LOW = "LOW"          # Safe / informational / allowlisted actions (auto-approved or low friction)
    MEDIUM = "MEDIUM"    # State-altering operations (may request confirmation)
    HIGH = "HIGH"        # Sensitive / system modifications (strictly requires explicit confirmation)
    CRITICAL = "CRITICAL"# Potentially dangerous/destructive actions (default DENY in Day 1)


@dataclass
class ToolResult:
    """Standardized result returned by any tool execution."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }


class BaseTool(ABC):
    """Abstract base class for all JARVIS tools."""

    name: str = ""
    description: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False

    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """Return JSON Schema for the tool's expected parameters."""
        pass

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with validated arguments."""
        pass

    def to_schema(self) -> Dict[str, Any]:
        """Return full schema representation for LLM function/tool calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.get_parameters_schema(),
            "risk_level": self.risk_level.value,
        }
