from __future__ import annotations

import asyncio
from collections import defaultdict
from enum import Enum
from typing import Any, Awaitable, Callable


class EventType(str, Enum):
    WAKE_WORD_DETECTED = "wake_word_detected"
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"
    TRANSCRIPTION_READY = "transcription_ready"
    LLM_RESPONSE = "llm_response"
    LLM_STREAM = "llm_stream"
    LLM_DONE = "llm_done"
    TTS_START = "tts_start"
    TTS_DONE = "tts_done"
    SKILL_EXECUTING = "skill_executing"
    SKILL_RESULT = "skill_result"
    ERROR = "error"
    STATE_CHANGE = "state_change"
    USER_INPUT = "user_input"
    SYSTEM_MESSAGE = "system_message"
    SHUTDOWN = "shutdown"


Handler = Callable[..., Awaitable[Any]]


class EventBus:
    def __init__(self):
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)
        self._queue: asyncio.Queue[tuple[EventType, dict[str, Any]]] = asyncio.Queue()
        self._running = False

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def publish(self, event_type: EventType, **data: Any) -> None:
        await self._queue.put((event_type, data))
        for handler in self._handlers[event_type]:
            try:
                await handler(**data)
            except Exception as e:
                await self.publish(EventType.ERROR, error=str(e), source=str(handler))

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        await self.publish(EventType.SHUTDOWN)
