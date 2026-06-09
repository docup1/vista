from __future__ import annotations

import asyncio
import re
import sys

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from brain.llm_client import LLMClient, parse_function_call
from brain.memory import Memory
from brain.prompts import build_system_prompt
from core.config import Config
from core.event_bus import EventBus, EventType
from skills.registry import SkillRegistry
from voice.stt import STTEngine
from voice.tts import TTSEngine


console = Console()


def _sanitize(text: str) -> str:
    """Remove surrogate characters that break JSON encoding."""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


_HALLUCINATION_PATTERNS = [
    r'\n\*\*Note:\*\*.*', r'\nЗапрос:\s*".*?"\n.*',
    r'\nCALL:.*→.*', r'<\|system\|>.*?</\|system\|>',
    r'<\|user\|>.*?</\|user\|>', r'\nПользователь:.*',
    r'\nUser:.*', r'## ДОСТУПНЫЕ ФУНКЦИИ.*',
    r'## ПРАВИЛА.*', r'## ЖЁСТКИЕ ЗАПРЕТЫ.*',
    r'Пример.*', r'пример.*', r'Доступные функции:.*',
    r'Доступно:.*', r'ПРАВИЛА:.*',
]

# Markers of hallucinated system prompt leakage
_RAMBLE_MARKERS = [
    "Пример запроса", "Пример использования", "Если пользовател",
    "Если запрос не связан", "Для действий пиши", "Доступные функции",
    "Доступно:", "CALL: функция", "Не пиши примеры",
    "Не продолжай диалог", "agent:", "Без примеров",
]


def _clean_response(text: str) -> str:
    """Strip hallucination patterns from LLM output."""
    for pattern in _HALLUCINATION_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

    # If text contains ramble markers, cut at the first one
    for marker in _RAMBLE_MARKERS:
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx]

    text = text.strip()
    if text.startswith("CALL:"):
        return text.split("\n")[0].strip()
    return text


def _is_ramble(text: str) -> bool:
    """Check if response is a hallucinated ramble (not a real reply)."""
    if len(text) < 2:
        return True
    for marker in _RAMBLE_MARKERS:
        if marker in text:
            return True
    # Too long = probably rambling
    if len(text) > 400 and text.count("\n") > 3:
        return True
    return False


class Orchestrator:
    def __init__(self):
        self.config = Config.get_instance()
        self.event_bus = EventBus()
        self.llm = LLMClient(self.config)
        self.memory = Memory(self.config)
        self.skills = SkillRegistry()
        self.stt: STTEngine | None = None
        self.tts: TTSEngine | None = None
        self._mode: str = "cli"
        self._running = False

    def setup(self, mode: str = "cli") -> None:
        self._mode = mode
        self.skills.auto_discover(self.config.skills_paths)

        if mode in ("voice", "daemon"):
            self.stt = STTEngine(self.config)
            self.tts = TTSEngine(self.config)
            # Pre-warm models at setup
            try:
                self.stt.load()
            except Exception:
                pass
            if self.config.tts_engine == "piper":
                try:
                    self.tts._load_piper()
                except Exception:
                    pass

    async def start(self) -> None:
        self._running = True
        await self.event_bus.start()

        console.print()
        console.print(Panel.fit(
            f"[bold cyan]{self.config.name}[/bold cyan] — локальный AI-ассистент\n"
            f"Модель: {self.config.llm_model}\n"
            f"Режим: {self._mode}\n"
            f"Скиллы: {', '.join(self.skills.list_skills().keys())}",
            title="🤖 Vista v0.2",
            border_style="cyan",
        ))

        # Check Ollama
        if self._mode != "voice":
            console.print("\n[yellow]Проверяю подключение к Ollama...[/yellow]")
            connected = await self.llm.check_connection()
            if connected:
                models = await self.llm.list_models()
                console.print(f"[green]Ollama подключен. Доступные модели:[/green] {', '.join(models[:5])}")
                if not any(self.config.llm_model.split(":")[0] in m for m in models):
                    console.print(f"\n[yellow]Модель {self.config.llm_model} не найдена. Загружаю...[/yellow]")
                    await self.llm.pull_model()
            else:
                console.print(
                    "[red]Ollama не запущен![/red]\n"
                    "Запустите: [bold]ollama serve[/bold] в другом терминале"
                )
                return

        if self._mode == "cli":
            await self._run_cli()
        elif self._mode == "voice":
            await self._run_voice()
        elif self._mode == "daemon":
            await self._run_daemon()
        elif self._mode == "once":
            await self._run_once()

    async def _run_cli(self) -> None:
        console.print("\n[dim]Введи /help для списка команд, Ctrl+C для выхода[/dim]\n")

        while self._running:
            try:
                user_input = console.input("[bold green]>> [/bold green]")
            except (KeyboardInterrupt, EOFError):
                break

            if not user_input.strip():
                continue

            user_input = _sanitize(user_input)

            if user_input.startswith("/"):
                await self._handle_command(user_input)
                continue

            await self._process_input(user_input)

        await self.shutdown()

    async def _handle_command(self, cmd: str) -> None:
        parts = cmd.split()
        command = parts[0].lower()

        if command == "/help":
            console.print(
                Panel(
                    "[bold]Команды:[/bold]\n"
                    "  /help     — это сообщение\n"
                    "  /clear    — очистить историю диалога\n"
                    "  /skills   — список доступных скиллов\n"
                    "  /history  — показать историю\n"
                    "  /model    — показать текущую модель\n"
                    "  /voice    — переключиться в голосовой режим\n"
                    "  /quit     — выход",
                    border_style="dim",
                )
            )
        elif command == "/clear":
            self.memory.clear_history()
            console.print("[yellow]История очищена.[/yellow]")
        elif command == "/skills":
            skills = self.skills.list_skills()
            for name, desc in skills.items():
                console.print(f"  [cyan]{name}[/cyan]: {desc}")
        elif command == "/history":
            history = self.memory.get_history()
            for msg in history[-10:]:
                role_mark = "🟢" if msg["role"] == "user" else "🤖"
                console.print(f"  {role_mark} {msg['content'][:100]}")
        elif command == "/model":
            console.print(f"[cyan]Модель:[/cyan] {self.config.llm_model}")
        elif command == "/voice":
            console.print("[yellow]Переключаюсь в голосовой режим...[/yellow]")
            await self._run_voice()
        elif command == "/quit":
            self._running = False
        else:
            console.print(f"[red]Неизвестная команда: {command}[/red]")

    def _match_quick_command(self, text: str) -> tuple[str | None, dict | None]:
        """Keyword-based command detection — runs before LLM for speed."""
        t = text.lower().strip()

        # Time
        if re.search(r'(который|сколько|скажи|текущее|сейчас)\s.*(час|врем|минут)', t):
            return "get_time", {}

        # Date
        if re.search(r'(какое|какой|какая|сегодня|текущая)\s.*(числ|дата|день|месяц|год|недел)', t) or \
           re.search(r'(дата|день\sнедели)', t) and 'рожден' not in t:
            return "get_date", {}

        # Calculate
        if re.search(r'(сколько|посчитай|вычисли|сосчитай)\s*(будет|получится)?', t) and \
           re.search(r'[\d+\-*/().^%]', t):
            return "calculate", {"expression": re.sub(r'[^0-9+*/().^%\-\s]', '', t)}

        # Launch app
        app_match = re.search(r'(запусти|открой|открыть|запустить)\s+(\w+)', t)
        if app_match:
            name = app_match.group(2).capitalize()
            return "launch_app", {"name": name}

        # System info
        if re.search(r'(систем|характеристик|желез|macOS|компьютер|процессор|память|оперативн)', t) and \
           re.search(r'(инфо|информаци|покажи|расскажи|какой|сколько|что\sза)', t):
            return "system_info", {}

        return None, None

    async def _process_input(self, user_input: str, use_tts: bool = False) -> str:
        user_input = _sanitize(user_input)

        await self.event_bus.publish(EventType.USER_INPUT, text=user_input)

        # Add to memory
        self.memory.add_conversation_turn("user", user_input)

        # ── Quick command detection (before LLM) ──
        func_name, params = self._match_quick_command(user_input)
        quick_result = None

        if func_name:
            console.print(f"\n[dim]⚙ {func_name}({params})[/dim]")
            quick_result = await self.skills.execute(func_name, **(params or {}))
            await self.event_bus.publish(EventType.SKILL_RESULT, skill=func_name, result=quick_result)
            if quick_result.message:
                console.print(f"[yellow]  ↳ {quick_result.message}[/yellow]")

            result_context = (
                f"[system] {func_name} → {quick_result.message}"
                if quick_result.success
                else f"[system] {func_name} ошибка: {quick_result.message}"
            )
            self.memory.add_conversation_turn("system", result_context)

        # ── Build LLM context ──
        system_msg = {"role": "system", "content": build_system_prompt(self.config, self.config.persona)}
        raw_context = self.memory.get_context_messages(user_input)

        token_budget = self.config.max_context_tokens
        context = []
        total_chars = len(system_msg["content"])
        for msg in reversed(raw_context):
            msg_chars = len(msg["content"])
            if total_chars + msg_chars > token_budget * 4:
                break
            context.insert(0, msg)
            total_chars += msg_chars

        messages = [system_msg] + context

        if quick_result:
            # Second instruction: just format the result naturally
            messages.append({"role": "system", "content": "Ответь одним предложением на русском, естественно."})
            console.print("\n[dim]Vista думает...[/dim]")
            try:
                response = await self.llm.chat(messages, stream=True)
            except Exception as e:
                console.print(f"\n[red]Ошибка LLM: {e}[/red]")
                fallback = quick_result.message or "Готово."
                console.print(f"[bold cyan]Vista:[/bold cyan] {fallback}")
                if use_tts and self.tts:
                    self.tts.speak_bg(fallback)
                return fallback
        else:
            # Normal conversation
            console.print("\n[dim]Vista думает...[/dim]")
            try:
                response = await self.llm.chat(messages, stream=True)
            except Exception as e:
                console.print(f"\n[red]Ошибка LLM: {e}[/red]")
                return f"Ошибка: {e}"

        # ── Stream and display ──
        full_response = ""
        try:
            async for chunk in response:
                full_response += chunk
                console.print(_sanitize(chunk), end="")
                if use_tts and self.tts:
                    for sep in (". ", "! ", "? "):
                        idx = chunk.find(sep)
                        if idx > 10:
                            sent = chunk[:idx + len(sep)].strip()
                            if sent:
                                self.tts.speak_bg(sent)
                            break
        except Exception as e:
            console.print(f"\n[red]Stream error: {e}[/red]")

        console.print("\n")
        full_response = _clean_response(full_response)

        # Fallback for empty/ramble
        if not full_response.strip() or _is_ramble(full_response):
            if quick_result:
                full_response = quick_result.message or "Готово."
            else:
                full_response = "Не понял запрос."

        # Speak remaining text
        if use_tts and self.tts and full_response.strip():
            self.tts.speak_bg(full_response.strip())

        # Store response
        self.memory.add_conversation_turn("assistant", full_response)
        return full_response

        # Store response
        self.memory.add_conversation_turn("assistant", full_response)

        return full_response

    async def _run_voice(self) -> None:
        if not self.stt or not self.tts:
            console.print("[red]Голос не настроен. pip install faster-whisper[/red]")
            return

        self._running = True

        console.print(
            "\n[yellow]Голосовой режим.[/yellow] Нажми [bold]Enter[/bold] — скажи фразу — пауза.\n"
            "[dim]Скажи 'стоп' для выхода.[/dim]\n"
        )

        while self._running:
            try:
                user_input = console.input("[bold green]🎤 Enter для записи...[/bold green]")
            except (KeyboardInterrupt, EOFError):
                break

            user_input = user_input.strip()
            if user_input.lower() in ("стоп", "stop", "выход", "exit", "q"):
                break

            console.print("[dim]🎙 Говори...[/dim]")
            text = ""
            try:
                text = await self.stt.listen_and_transcribe(
                    duration=None,
                    on_speech_start=lambda: console.print("[green]●[/green] ", end=""),
                    on_speech_end=lambda: console.print("[dim]○[/dim]"),
                )
            except Exception as e:
                console.print(f"\n[red]STT: {e}[/red]")
                continue

            text = (text or "").strip()
            if len(text) < 2:
                console.print("[dim]  (тишина)[/dim]")
                continue

            console.print(f"\n[bold green]Вы:[/bold green] {text}")

            if text.lower() in ("стоп", "stop", "выход"):
                break

            await self._process_input(text, use_tts=True)
            await self.tts.wait_done()  # don't listen while speaking

        console.print("[yellow]Голосовой режим завершён[/yellow]")

    async def _run_daemon(self) -> None:
        """Background mode: listen for wake word, then enter active dialogue."""
        if not self.stt or not self.tts:
            console.print("[red]Голос не настроен. pip install faster-whisper[/red]")
            return

        self._running = True

        wake_words = [w.lower() for w in self.config.wake_words]
        active_timeout = self.config.get("daemon.active_timeout", 15.0)

        console.print(Panel.fit(
            f"[bold green]🐚 Фоновый режим[/bold green]\n"
            f"Wake-слова: {', '.join(wake_words)}\n"
            "Скажи wake-слово → активный диалог\n"
            f"Молчи {active_timeout:.0f} сек в диалоге → обратно в фон\n"
            "Скажи 'стоп' для выхода из диалога\n"
            "Ctrl+C для полного выхода",
            border_style="green",
        ))

        while self._running:
            # ── IDLE: listen for wake word ──
            console.print("\n[dim]💤 Фон — жду wake-слово...[/dim]", end="\r")
            try:
                text = await self.stt.listen_and_transcribe(
                    duration=None,
                    on_speech_start=lambda: console.print("[green]●[/green] ", end=""),
                    on_speech_end=lambda: console.print("[dim]○[/dim]"),
                )
            except Exception as e:
                console.print(f"\n[red]STT: {e}[/red]")
                await asyncio.sleep(1)
                continue

            text = (text or "").strip()
            if len(text) < 2:
                continue

            text_lower = text.lower()
            # Check for wake word (exact or fuzzy), track position
            woke = False
            wake_end = 0
            for ww in wake_words:
                idx = text_lower.find(ww)
                if idx >= 0:
                    woke = True
                    wake_end = idx + len(ww)
                    break
                # Fuzzy: 1-char difference
                if len(ww) >= 3:
                    for i in range(len(text_lower) - len(ww) + 1):
                        window = text_lower[i:i + len(ww)]
                        same = sum(1 for a, b in zip(window, ww) if a == b)
                        if same >= len(ww) - 1:
                            woke = True
                            wake_end = i + len(ww)
                            break
                if woke:
                    break

            if not woke:
                snippet = text[:80] + ("..." if len(text) > 80 else "")
                console.print(f"\n[dim]  💤 слышу: \"{snippet}\"[/dim]")
                console.print("[dim]  (скажи 'виста' или 'джарвис' для активации)[/dim]")
                continue

            # ── WOKE: enter active dialogue ──
            # Extract command: everything after the wake word
            after = text[wake_end:].strip().lstrip(".,!? :-")
            command_part = after if len(after) > 2 else ""

            # Enter active dialogue and process the first utterance
            last_active = asyncio.get_event_loop().time()
            active = True

            if command_part:
                console.print(f"[bold green]Вы:[/bold green] {command_part}")
                await self._process_input(command_part, use_tts=True)
                await self.tts.wait_done()

            # ── ACTIVE: process follow-up commands until timeout ──
            while active and self._running:
                elapsed = asyncio.get_event_loop().time() - last_active
                remaining = active_timeout - elapsed
                if remaining <= 0:
                    console.print(f"\n[dim]⏰ Таймаут — возврат в фон[/dim]")
                    break

                console.print(f"\n[bold green]🎤 Диалог[/bold green] [dim]({remaining:.0f}с)[/dim] [dim]слушаю...[/dim]", end="\r")
                try:
                    text = await self.stt.listen_and_transcribe(
                        duration=None,
                        on_speech_start=lambda: console.print("[green]●[/green] ", end=""),
                        on_speech_end=lambda: console.print("[dim]○[/dim]"),
                    )
                except Exception as e:
                    console.print(f"\n[red]STT: {e}[/red]")
                    await asyncio.sleep(1)
                    continue

                text = (text or "").strip()
                if len(text) < 2:
                    continue

                last_active = asyncio.get_event_loop().time()

                console.print(f"\n[bold green]Вы:[/bold green] {text}")

                if text.lower() in ("стоп", "stop", "выход", "хватит", "пока"):
                    console.print("[yellow]Выход из диалога[/yellow]")
                    active = False
                    break

                await self._process_input(text, use_tts=True)
                await self.tts.wait_done()  # don't listen while speaking

            console.print("[dim]💤 Возврат в фон[/dim]")

        console.print("[yellow]Фоновый режим завершён[/yellow]")

    async def _run_once(self) -> None:
        user_input = console.input("[bold green]>> [/bold green]")
        await self._process_input(user_input, use_tts=False)
        await self.shutdown()

    async def shutdown(self) -> None:
        self._running = False
        await self.llm.close()
        await self.event_bus.stop()
        console.print("\n[dim]Vista завершает работу. До связи![/dim]")


# Singleton
_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
