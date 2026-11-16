"""
Base Interface for Procedural Application Skills & Playbooks
All specialized application playbooks inherit from BaseSkill.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class BaseSkill(ABC):
    """
    Abstract contract for high-speed procedural playbooks.
    Encapsulates application-specific deterministic hotkeys, window management,
    and workflow macros.
    """
    name: str = "base"
    description: str = "Base procedural skill"

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if the target application is installed and accessible on this system."""
        pass

    @abstractmethod
    def get_supported_actions(self) -> Dict[str, str]:
        """Returns a dictionary of action names mapped to concise human-readable descriptions."""
        pass

    @abstractmethod
    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes the requested procedural action.
        Returns a dictionary containing:
        - status: 'success' | 'error' | 'fallback'
        - message: Human-readable execution feedback
        - active_window: Optional title or state description
        """
        pass
