from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillParameter:
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass
class SkillResult:
    success: bool
    data: Any = None
    error: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "message": self.message,
        }


class BaseSkill(ABC):
    name: str = ""
    description: str = ""
    parameters: list[SkillParameter] = field(default_factory=list)

    @abstractmethod
    async def execute(self, **kwargs: Any) -> SkillResult: ...

    def to_llm_description(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                p.name: {
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                }
                for p in self.parameters
            },
        }
