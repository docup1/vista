import asyncio
import platform
import subprocess
from pathlib import Path
from typing import Any

from skills.base import BaseSkill, SkillParameter, SkillResult


class LaunchAppSkill(BaseSkill):
    name = "launch_app"
    description = "Запустить приложение на macOS"
    parameters = [
        SkillParameter(name="name", description="Название приложения (например Safari, Terminal, Finder)")
    ]

    async def execute(self, **kwargs: Any) -> SkillResult:
        name = kwargs.get("name", "")
        if not name:
            return SkillResult(success=False, message="Укажи название приложения")

        try:
            proc = await asyncio.create_subprocess_exec(
                "open", "-a", name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return SkillResult(success=True, message=f"Запускаю {name}")
            else:
                err = stderr.decode().strip()
                # Try with .app extension
                if not name.endswith(".app"):
                    proc2 = await asyncio.create_subprocess_exec(
                        "open", "-a", f"{name}.app",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await proc2.communicate()
                    if proc2.returncode == 0:
                        return SkillResult(success=True, message=f"Запускаю {name}")
                return SkillResult(
                    success=False,
                    message=f"Не удалось запустить {name}: {err or 'приложение не найдено'}",
                )
        except Exception as e:
            return SkillResult(success=False, message=f"Ошибка: {e}")


class SystemInfoSkill(BaseSkill):
    name = "system_info"
    description = "Получить информацию о системе (macOS, CPU, память)"
    parameters = []

    async def execute(self, **kwargs: Any) -> SkillResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "sysctl", "-n", "machdep.cpu.brand_string",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            cpu = stdout.decode().strip()

            proc = await asyncio.create_subprocess_exec(
                "sw_vers",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            mac_ver = {}
            for line in stdout.decode().strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    mac_ver[k.strip()] = v.strip()

            proc = await asyncio.create_subprocess_exec(
                "sysctl", "-n", "hw.memsize",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            mem_bytes = int(stdout.decode().strip())
            mem_gb = mem_bytes / (1024**3)

            info = (
                f"macOS {mac_ver.get('ProductVersion', '?')} ({mac_ver.get('BuildVersion', '?')})\n"
                f"CPU: {cpu}\n"
                f"RAM: {mem_gb:.0f} GB\n"
                f"Arch: {platform.machine()}"
            )
            return SkillResult(success=True, data=info, message=info)
        except Exception as e:
            return SkillResult(success=False, message=f"Ошибка: {e}")


class ReadFileSkill(BaseSkill):
    name = "read_file"
    description = "Прочитать содержимое файла"
    parameters = [
        SkillParameter(name="path", description="Путь к файлу")
    ]

    async def execute(self, **kwargs: Any) -> SkillResult:
        path = kwargs.get("path", "")
        if not path:
            return SkillResult(success=False, message="Укажи путь к файлу")

        p = Path(path).expanduser()
        if not p.exists():
            return SkillResult(success=False, message=f"Файл не найден: {path}")
        if p.is_dir():
            try:
                items = list(p.iterdir())
                names = [f"  {'📁' if i.is_dir() else '📄'} {i.name}" for i in items[:50]]
                content = "\n".join(names)
                if len(items) > 50:
                    content += f"\n  ... и ещё {len(items) - 50} элементов"
                return SkillResult(success=True, data=content, message=f"Содержимое {path}:\n{content}")
            except PermissionError:
                return SkillResult(success=False, message=f"Нет доступа к {path}")

        try:
            content = p.read_text(encoding="utf-8")
            if len(content) > 2000:
                content = content[:2000] + f"\n... (обрезано, всего {len(content)} символов)"
            return SkillResult(success=True, data=content, message=f"{path}:\n{content}")
        except Exception as e:
            return SkillResult(success=False, message=f"Не удалось прочитать: {e}")


class WriteFileSkill(BaseSkill):
    name = "write_file"
    description = "Записать содержимое в файл"
    parameters = [
        SkillParameter(name="path", description="Путь к файлу"),
        SkillParameter(name="content", description="Содержимое для записи"),
    ]

    async def execute(self, **kwargs: Any) -> SkillResult:
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        if not path or not content:
            return SkillResult(success=False, message="Укажи путь и содержимое")

        p = Path(path).expanduser()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return SkillResult(success=True, message=f"Записано в {path} ({len(content)} символов)")
        except Exception as e:
            return SkillResult(success=False, message=f"Не удалось записать: {e}")


class OpenURLSkill(BaseSkill):
    name = "open_url"
    description = "Открыть URL в браузере"
    parameters = [
        SkillParameter(name="url", description="URL для открытия")
    ]

    async def execute(self, **kwargs: Any) -> SkillResult:
        url = kwargs.get("url", "")
        if not url:
            return SkillResult(success=False, message="Укажи URL")

        try:
            proc = await asyncio.create_subprocess_exec(
                "open", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return SkillResult(success=True, message=f"Открываю {url}")
        except Exception as e:
            return SkillResult(success=False, message=f"Ошибка: {e}")
