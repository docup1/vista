import asyncio
import os
from typing import Any

from skills.base import BaseSkill, SkillParameter, SkillResult


class RunShellSkill(BaseSkill):
    name = "run_shell"
    description = "Выполнить команду в терминале и вернуть результат"
    parameters = [
        SkillParameter(name="command", description="Команда для выполнения")
    ]

    async def execute(self, **kwargs: Any) -> SkillResult:
        command = kwargs.get("command", "")
        if not command:
            return SkillResult(success=False, message="Укажи команду")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd(),
            )
            stdout, stderr = await proc.communicate()
            output = stdout.decode().strip()
            error = stderr.decode().strip()

            if proc.returncode == 0:
                result = output or "(выполнено успешно)"
                return SkillResult(success=True, data=result, message=result)
            else:
                msg = error or output or f"Код возврата: {proc.returncode}"
                return SkillResult(success=False, data=msg, message=f"Ошибка: {msg}")
        except Exception as e:
            return SkillResult(success=False, message=f"Ошибка выполнения: {e}")


class GitStatusSkill(BaseSkill):
    name = "git_status"
    description = "Показать статус git-репозитория в текущей директории"
    parameters = []

    async def execute(self, **kwargs: Any) -> SkillResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "status", "--short",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd(),
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err = stderr.decode().strip()
                return SkillResult(success=False, message=f"Не git-репозиторий: {err}")

            output = stdout.decode().strip()
            if not output:
                return SkillResult(success=True, message="Чисто, изменений нет")

            return SkillResult(success=True, data=output, message=f"Git status:\n{output}")
        except Exception as e:
            return SkillResult(success=False, message=f"Ошибка: {e}")


class GitDiffSkill(BaseSkill):
    name = "git_diff"
    description = "Показать изменения в git (unstaged)"
    parameters = []

    async def execute(self, **kwargs: Any) -> SkillResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "--stat",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd(),
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err = stderr.decode().strip()
                return SkillResult(success=False, message=f"Ошибка: {err}")

            output = stdout.decode().strip()
            if not output:
                return SkillResult(success=True, message="Изменений в рабочей директории нет")

            return SkillResult(success=True, data=output, message=f"Git diff:\n{output}")
        except Exception as e:
            return SkillResult(success=False, message=f"Ошибка: {e}")


class GitLogSkill(BaseSkill):
    name = "git_log"
    description = "Показать историю git-коммитов"
    parameters = [
        SkillParameter(name="count", type="number", description="Количество коммитов", required=False, default=5)
    ]

    async def execute(self, **kwargs: Any) -> SkillResult:
        count = kwargs.get("count", 5)
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "log", f"-{count}", "--oneline", "--no-decorate",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd(),
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err = stderr.decode().strip()
                return SkillResult(success=False, message=f"Ошибка: {err}")

            output = stdout.decode().strip()
            if not output:
                return SkillResult(success=True, message="Коммитов нет")

            return SkillResult(success=True, data=output, message=f"Последние коммиты:\n{output}")
        except Exception as e:
            return SkillResult(success=False, message=f"Ошибка: {e}")
