from abc import ABC, abstractmethod


class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, params: dict) -> dict:
        """Execute the tool with structured parameters."""
