from __future__ import annotations

import asyncio
import re
import subprocess
import wave
from pathlib import Path

from core.config import Config

# Default voice mapping: language → voice name
_DEFAULT_VOICES = {
    "ru": "Milena",
    "en": "Samantha",
}

_RU_VOICES = ["Katya", "Milena", "Yuri"]

# ── English → Cyrillic transliteration for Piper ──────────────────

# Known words — dictionary override (most common tech terms)
_TRANSLIT_DICT = {
    # Assistant self-name
    "Vista": "Виста",
    "vista": "виста",
    "EDITH": "Эдит",
    "edith": "эдит",
    # macOS
    "macOS": "макОС", "macos": "макОС", "MacOS": "МакОС",
    "Safari": "Сафари", "safari": "сафари",
    "Chrome": "Хром", "chrome": "хром",
    "Firefox": "Файрфокс", "firefox": "файрфокс",
    "Finder": "Файндер", "finder": "файндер",
    "Terminal": "Терминал", "terminal": "терминал",
    "Xcode": "ИксКод", "xcode": "икскод",
    # Dev
    "GitHub": "ГитХаб", "github": "гитхаб",
    "git": "гит", "Git": "Гит",
    "Python": "Пайтон", "python": "пайтон",
    "JavaScript": "ДжаваСкрипт", "javascript": "джаваскрипт",
    "TypeScript": "ТайпСкрипт", "typescript": "тайпскрипт",
    "Node": "Нод", "node": "нод",
    "Docker": "Докер", "docker": "докер",
    "JSON": "ДжейСон", "json": "джейсон",
    "API": "АПИ", "api": "апи",
    "URL": "ЮРЛ", "url": "юрл",
    "HTTP": "АшТиТиПи", "http": "аштитипи",
    "HTML": "АшТиЭмЭл", "html": "аштиэмэл",
    "CSS": "СиЭсЭс", "css": "сиэсэс",
    "SQL": "ЭсКюЭл", "sql": "эскюэл",
    "SSH": "ЭсЭсАш", "ssh": "эсэсаш",
    "status": "статус", "Status": "Статус",
    "branch": "бранч", "Branch": "Бранч",
    "commit": "коммит", "Commit": "Коммит",
    "push": "пуш", "Push": "Пуш",
    "pull": "пул", "Pull": "Пул",
    "merge": "мерж", "Merge": "Мерж",
    "main": "мейн", "Main": "Мейн",
    "master": "мастер", "Master": "Мастер",
    "server": "сервер", "Server": "Сервер",
    "error": "эррор", "Error": "Эррор",
    "file": "файл", "File": "Файл",
    "files": "файлы", "Files": "Файлы",
    "app": "апп", "App": "Апп",
    "OK": "Окей", "ok": "окей", "Ok": "Ок",
    "AI": "Ай", "ai": "ай",
    # Apple
    "iPhone": "Айфон", "iphone": "айфон",
    "iPad": "Айпад", "ipad": "айпад",
    "Apple": "Эпл", "apple": "эпл",
    "Intel": "Интел", "intel": "интел",
    # Hardware
    "CPU": "СиПиЮ", "cpu": "сипию",
    "GPU": "ДжиПиЮ", "gpu": "джипию",
    "RAM": "РАМ", "ram": "рам",
    "SSD": "ЭсЭсДи", "ssd": "эсэсди",
    "GB": "Гигабайт", "gb": "гигабайт",
    "MB": "Мегабайт", "mb": "мегабайт",
    "TB": "Терабайт", "tb": "терабайт",
    # Apple Silicon
    "M1": "Эм Один", "M2": "Эм Два", "M3": "Эм Три", "M4": "Эм Четыре",
    # Common English words in Russian context
    "hello": "хелло", "Hello": "Хелло",
    "world": "ворлд", "World": "Ворлд",
    "test": "тест", "Test": "Тест",
    "debug": "дебаг", "Debug": "Дебаг",
    "source": "сорс", "Source": "Сорс",
    "code": "код", "Code": "Код",
    "data": "дата", "Data": "Дата",
    "user": "юзер", "User": "Юзер",
    "home": "хоум", "Home": "Хоум",
    "time": "тайм", "Time": "Тайм",
    "date": "дейт", "Date": "Дейт",
    "mode": "мод", "Mode": "Мод",
    "name": "нейм", "Name": "Нейм",
    "path": "пас", "Path": "Пас",
    "command": "комманд", "Command": "Комманд",
    "shell": "шелл", "Shell": "Шелл",
    "config": "конфиг", "Config": "Конфиг",
    "default": "дефолт", "Default": "Дефолт",
    "arch": "арч", "Arch": "Арч",
    "arm64": "арм64", "ARM64": "АРМ64",
    # File extensions & common shorts
    "py": "пай", "Py": "Пай",
    "js": "джейэс", "Js": "ДжейЭс",
    "ts": "тиэс", "Ts": "ТиЭс",
    "go": "го", "Go": "Го",
    "rs": "раст", "Rs": "Раст",
    "sh": "ш", "Sh": "Ш",
    "yml": "ямл", "Yml": "Ямл",
    "yaml": "ямл", "Yaml": "Ямл",
    "toml": "томл", "Toml": "Томл",
    "json": "джейсон", "Json": "Джейсон",
    "md": "эмди", "Md": "ЭмДи",
    "txt": "тхт", "Txt": "Тхт",
    "log": "лог", "Log": "Лог",
    "env": "энв", "Env": "Энв",
    "src": "срк", "Src": "Срк",
    "lib": "либ", "Lib": "Либ",
    "bin": "бин", "Bin": "Бин",
    "etc": "итс", "Etc": "Итс",
    "tmp": "тмп", "Tmp": "Тмп",
    "var": "вар", "Var": "Вар",
    "doc": "док", "Doc": "Док",
    "changed": "изменён", "Changed": "Изменён",
    "changes": "изменения", "Changes": "Изменения",
}

# Letter-by-letter fallback
_LATIN_TO_CYRILLIC = str.maketrans({
    'A': 'Э', 'a': 'а', 'B': 'Б', 'b': 'б', 'C': 'К', 'c': 'к',
    'D': 'Д', 'd': 'д', 'E': 'Е', 'e': 'е', 'F': 'Ф', 'f': 'ф',
    'G': 'Г', 'g': 'г', 'H': 'Х', 'h': 'х', 'I': 'И', 'i': 'и',
    'J': 'Д', 'j': 'дж', 'K': 'К', 'k': 'к', 'L': 'Л', 'l': 'л',
    'M': 'М', 'm': 'м', 'N': 'Н', 'n': 'н', 'O': 'О', 'o': 'о',
    'P': 'П', 'p': 'п', 'Q': 'К', 'q': 'к', 'R': 'Р', 'r': 'р',
    'S': 'С', 's': 'с', 'T': 'Т', 't': 'т', 'U': 'У', 'u': 'у',
    'V': 'В', 'v': 'в', 'W': 'В', 'w': 'в', 'X': 'Кс', 'x': 'кс',
    'Y': 'Й', 'y': 'й', 'Z': 'З', 'z': 'з',
})


def _transliterate(text: str) -> str:
    """Convert Latin words in text to Cyrillic approximation for Piper Russian voices."""
    # Strip markdown formatting
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)

    # Strip unpronounceable symbols
    text = text.replace("×", " умножить на ")
    text = text.replace("*", " умножить на ")
    text = text.replace("^", " в степени ")
    text = text.replace("≈", " примерно ")
    text = text.replace("±", " плюс-минус ")
    text = text.replace("√", " корень из ")
    text = text.replace("∑", " сумма ")
    text = text.replace("∫", " интеграл ")
    text = text.replace("~", " примерно ")
    text = text.replace("→", " стремится к ")
    text = text.replace("←", " ")
    text = re.sub(r'[\U0001F300-\U0001F9FF]', '', text)  # emoji

    # Strip URLs
    text = re.sub(r'https?://\S+', ' ссылка ', text)

    # Protect file paths — don't transliterate
    paths = {}
    def save_path(m: re.Match) -> str:
        key = f"PATH{len(paths)}"
        paths[key] = m.group(0)
        return key

    text = re.sub(r'/(?:[\w.-]+/)+[\w.-]+', save_path, text)

    # Protect numbers with units
    text = re.sub(r'(\d+)\s*(GB|MB|KB|TB|GHz|MHz)', r'\1 \2', text)

    def replace_word(m: re.Match) -> str:
        word = m.group(0)
        # Check if this was a saved path key
        if word in paths:
            return word
        if word in _TRANSLIT_DICT:
            return _TRANSLIT_DICT[word]
        # Alphanumeric like "M4", "3D", "A1"
        if re.match(r'^[a-zA-Z0-9]+$', word) and any(c.isalpha() for c in word):
            result = []
            for ch in word:
                if ch.isdigit():
                    result.append(ch)
                else:
                    result.append(ch.translate(_LATIN_TO_CYRILLIC))
            return ''.join(result)
        # Pure Latin words (2+ chars)
        if word.isascii() and len(word) >= 2 and word.isalpha():
            return word.translate(_LATIN_TO_CYRILLIC)
        return word

    # Replace Latin tokens
    text = re.sub(r'\b[a-zA-Z][a-zA-Z0-9]*\b', replace_word, text)

    # Restore file paths
    for key, path in paths.items():
        text = text.replace(key, path)

    # Clean up artifacts
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


class TTSEngine:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.get_instance()
        self._engine = self.config.tts_engine
        self._voice = self.config.tts_voice
        self._piper: "PiperVoice | None" = None  # noqa: F821
        self._pending_tasks: list[asyncio.Task] = []

    def _load_piper(self):
        if self._piper is not None:
            return
        from piper import PiperVoice

        model_dir = Path(self.config.get("models.tts.piper_model_dir", "./data/piper"))
        model_file = model_dir / f"{self._voice}.onnx"
        if not model_file.exists():
            raise FileNotFoundError(
                f"Piper model not found: {model_file}\n"
                f"Download: mkdir -p data/piper && cd data/piper && "
                f"curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/"
                f"ruslan/medium/{self._voice}.onnx && "
                f"curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/"
                f"ruslan/medium/{self._voice}.onnx.json"
            )
        self._piper = PiperVoice.load(str(model_file))

    @staticmethod
    def list_voices(lang: str | None = None) -> list[str]:
        """List available macOS say voices."""
        voices = set()
        try:
            result = subprocess.run(
                ["say", "-v", "?"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split("\n"):
                parts = line[:60].split()
                if len(parts) >= 2:
                    name, voice_lang = parts[0], parts[1]
                    if lang and not voice_lang.startswith(lang):
                        continue
                    voices.add(name)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        for name in (["Katya", "Milena", "Yuri"] if lang == "ru" else []):
            try:
                subprocess.run(["say", "-v", name, "test"], capture_output=True, timeout=3)
                voices.add(name)
            except Exception:
                pass

        return sorted(voices)

    @staticmethod
    def test_voice(voice: str, text: str = "Привет! Я EDITH.", rate: int = 190) -> None:
        subprocess.run(["say", "-v", voice, "-r", str(rate), text], timeout=30)

    def _resolve_say_voice(self) -> str:
        if self._voice and self._voice != "auto":
            return self._voice
        lang = self.config.stt_language
        if lang == "ru":
            available = self.list_voices("ru")
            for v in _RU_VOICES:
                if v in available:
                    return v
            return "Milena"
        return _DEFAULT_VOICES.get(lang, "Samantha")

    async def speak(self, text: str) -> None:
        if not text or not text.strip():
            return

        if self._engine == "piper":
            try:
                await self._speak_piper(text)
            except Exception as e:
                print(f"[tts] Piper failed ({e}), falling back to macOS say")
                await self._speak_macos(text)
        else:
            await self._speak_macos(text)

    def speak_bg(self, text: str) -> None:
        """Fire-and-forget speech — returns immediately."""
        if not text or not text.strip():
            return
        task = asyncio.create_task(self.speak(text))
        self._pending_tasks.append(task)
        # Clean up completed tasks
        self._pending_tasks = [t for t in self._pending_tasks if not t.done()]

    async def wait_done(self) -> None:
        """Wait for all queued speech to finish — prevents mic picking up TTS."""
        pending = [t for t in self._pending_tasks if not t.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._pending_tasks.clear()

    async def _speak_macos(self, text: str) -> None:
        voice = self._resolve_say_voice()
        rate = str(self.config.get("models.tts.rate", 190))
        proc = await asyncio.create_subprocess_exec(
            "say", "-v", voice, "-r", rate, text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()

    async def _speak_piper(self, text: str) -> None:
        self._load_piper()

        # Transliterate English to Cyrillic — Piper ru voice can't read Latin
        text = _transliterate(text)

        import tempfile, os

        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        with wave.open(tmp, "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self._piper.config.sample_rate)
            self._piper.synthesize_wav(text, wav_file)

        proc = await asyncio.create_subprocess_exec(
            "afplay", tmp,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        os.unlink(tmp)

    async def speak_stream(self, text: str, callback=None) -> None:
        for chunk in self._split_for_speech(text):
            await self.speak(chunk)
            if callback:
                callback(chunk)

    def _split_for_speech(self, text: str, max_len: int = 300) -> list[str]:
        sentences = (
            text.replace("!", "!|").replace("?", "?|").replace(".\n", ".|").split("|")
        )
        chunks = []
        current = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(current) + len(s) < max_len:
                current += " " + s if current else s
            else:
                if current:
                    chunks.append(current.strip())
                current = s
        if current:
            chunks.append(current.strip())
        return chunks if chunks else [text]
