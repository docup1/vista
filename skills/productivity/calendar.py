from datetime import datetime
from typing import Any

from skills.base import BaseSkill, SkillParameter, SkillResult


class GetTimeSkill(BaseSkill):
    name = "get_time"
    description = "Получить текущее время"
    parameters = []

    async def execute(self, **kwargs: Any) -> SkillResult:
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        return SkillResult(success=True, data=time_str, message=f"Сейчас {time_str}")


class GetDateSkill(BaseSkill):
    name = "get_date"
    description = "Получить текущую дату"
    parameters = []

    async def execute(self, **kwargs: Any) -> SkillResult:
        now = datetime.now()
        months = [
            "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря",
        ]
        weekdays = [
            "понедельник", "вторник", "среда", "четверг",
            "пятница", "суббота", "воскресенье",
        ]
        date_str = f"{now.day} {months[now.month - 1]} {now.year}, {weekdays[now.weekday()]}"
        return SkillResult(success=True, data=date_str, message=f"Сегодня {date_str}")


class CalculateSkill(BaseSkill):
    name = "calculate"
    description = "Вычислить математическое выражение"
    parameters = [
        SkillParameter(name="expression", description="Математическое выражение (например 2+2*3)")
    ]

    async def execute(self, **kwargs: Any) -> SkillResult:
        expression = kwargs.get("expression", "")
        if not expression:
            return SkillResult(success=False, message="Укажи выражение")

        allowed_chars = set("0123456789+-*/().^% **")
        safe = "".join(c for c in expression if c in allowed_chars or c == " ")
        try:
            result = eval(safe, {"__builtins__": {}}, {})
            return SkillResult(success=True, data=result, message=f"{expression} = {result}")
        except Exception as e:
            return SkillResult(success=False, message=f"Не могу вычислить: {e}")
