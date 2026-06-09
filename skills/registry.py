from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from skills.base import BaseSkill, SkillResult


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> None:
        self._skills.pop(name, None)

    def get(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def list_skills(self) -> dict[str, str]:
        return {name: skill.description for name, skill in self._skills.items()}

    def get_llm_descriptions(self) -> list[dict[str, Any]]:
        return [skill.to_llm_description() for skill in self._skills.values()]

    async def execute(self, skill_name: str, **params: Any) -> SkillResult:
        skill = self._skills.get(skill_name)
        if not skill:
            return SkillResult(
                success=False,
                error=f"Unknown skill: {skill_name}",
                message=f"Я не знаю команды '{skill_name}'",
            )
        try:
            return await skill.execute(**params)
        except Exception as e:
            return SkillResult(
                success=False,
                error=str(e),
                message=f"Ошибка при выполнении {skill_name}: {e}",
            )

    def auto_discover(self, paths: list[str]) -> None:
        for path in paths:
            try:
                package = importlib.import_module(path)
                for _, module_name, _ in pkgutil.iter_modules(package.__path__):
                    module = importlib.import_module(f"{path}.{module_name}")
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, BaseSkill)
                            and attr is not BaseSkill
                        ):
                            skill = attr()
                            self.register(skill)
            except (ImportError, AttributeError) as e:
                print(f"  [warn] Could not load skills from {path}: {e}")
