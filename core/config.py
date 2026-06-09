from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class Config:
    _instance: Config | None = None

    def __init__(self, config_path: str | Path = "config.yaml"):
        self.config_path = Path(config_path)
        self._data: dict[str, Any] = {}
        self.load()

    @classmethod
    def get_instance(cls) -> Config:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self) -> None:
        if self.config_path.exists():
            with open(self.config_path) as f:
                self._data = yaml.safe_load(f) or {}
        self._apply_env_overrides()

    def _apply_env_overrides(self) -> None:
        overrides = {
            "models.llm.model": "EDITH_LLM_MODEL",
            "models.llm.host": "EDITH_LLM_HOST",
            "models.stt.model_size": "EDITH_STT_MODEL",
            "models.stt.language": "EDITH_STT_LANG",
            "models.tts.engine": "EDITH_TTS_ENGINE",
            "models.tts.voice": "EDITH_TTS_VOICE",
            "memory.persist_dir": "EDITH_MEMORY_DIR",
        }
        for key, env_var in overrides.items():
            value = os.environ.get(env_var)
            if value:
                self._set_nested(key, value)

    def _set_nested(self, key: str, value: Any) -> None:
        keys = key.split(".")
        d = self._data
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        d = self._data
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    @property
    def name(self) -> str:
        return self.get("edith.name", "Vista")

    @property
    def persona(self) -> str:
        return self.get("edith.persona", "concise")

    @property
    def wake_words(self) -> list[str]:
        return self.get("edith.wake_words", ["эдит", "edith"])

    @property
    def llm_model(self) -> str:
        return self.get("models.llm.model", "phi3:3.8b")

    @property
    def llm_host(self) -> str:
        return self.get("models.llm.host", "http://localhost:11434")

    @property
    def llm_temperature(self) -> float:
        return self.get("models.llm.temperature", 0.7)

    @property
    def llm_max_tokens(self) -> int:
        return self.get("models.llm.max_tokens", 512)

    @property
    def llm_context_window(self) -> int:
        return self.get("models.llm.context_window", 2048)

    @property
    def llm_stop_tokens(self) -> list[str]:
        return self.get("models.llm.stop_tokens", ["\nПользователь:", "\nUser:"])

    @property
    def stt_model_size(self) -> str:
        return self.get("models.stt.model_size", "tiny")

    @property
    def stt_language(self) -> str:
        return self.get("models.stt.language", "ru")

    @property
    def tts_engine(self) -> str:
        return self.get("models.tts.engine", "piper")

    @property
    def tts_voice(self) -> str:
        return self.get("models.tts.voice", "ru_RU-ruslan-medium")

    @property
    def embeddings_model(self) -> str:
        return self.get("models.embeddings.model", "nomic-embed-text")

    @property
    def memory_collection(self) -> str:
        return self.get("memory.collection_name", "edith_memory")

    @property
    def memory_persist_dir(self) -> str:
        return self.get("memory.persist_dir", "./data/chroma")

    @property
    def max_context_messages(self) -> int:
        return self.get("memory.max_context_messages", 10)

    @property
    def max_context_tokens(self) -> int:
        return self.get("memory.max_context_tokens", 1500)

    @property
    def summarize_threshold(self) -> int:
        return self.get("memory.summarize_threshold", 8)

    @property
    def debug(self) -> bool:
        return self.get("debug", False)

    @property
    def daemon_no_wake(self) -> bool:
        return self.get("daemon.no_wake", False)

    @property
    def sample_rate(self) -> int:
        return self.get("voice.sample_rate", 16000)

    @property
    def skills_paths(self) -> list[str]:
        return self.get("skills.paths", ["skills.system", "skills.dev"])
