from __future__ import annotations

import asyncio
import time
from enum import Enum, auto

import numpy as np
import sounddevice as sd

from core.config import Config
from voice.stt import STTEngine, _find_input_device


class State(Enum):
    IDLE = auto()
    WAKING = auto()
    ACTIVE = auto()
    COOLDOWN = auto()


class BackgroundListener:
    def __init__(
        self,
        config: Config | None = None,
        stt: STTEngine | None = None,
        tts=None,
        on_wake: callable | None = None,
        on_command: callable | None = None,
        on_state_change: callable | None = None,
    ):
        self.config = config or Config.get_instance()
        self.stt = stt or STTEngine(self.config)
        self.tts = tts
        self._on_wake = on_wake
        self._on_command = on_command
        self._on_state_change = on_state_change

        self._state = State.IDLE
        self._running = False
        self._sr = self.config.sample_rate
        self._device = _find_input_device()

        self._active_timeout = self.config.get("daemon.active_timeout", 15.0)
        self._cooldown_timeout = self.config.get("daemon.cooldown_timeout", 30.0)
        self._wake_chunk_dur = self.config.get("daemon.wake_chunk_duration", 2.0)
        self._silence_threshold = self.config.get("voice.silence_threshold", 100)
        self._wake_words = [w.lower() for w in self.config.wake_words]
        self._no_wake = self.config.get("daemon.no_wake", False)  # skip wake word, always active
        self._debug = self.config.debug

        self._last_speech_time = 0.0
        self._last_state_change = 0.0
        self._active_mode = False

        # Thread-safe: main loop to schedule async callbacks
        self._loop: asyncio.AbstractEventLoop | None = None

        # Pre-load STT model in background
        try:
            self.stt._load_model()
        except Exception:
            pass

    @property
    def state(self) -> State:
        return self._state

    async def start(self) -> None:
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._set_state(State.IDLE)

        # Run the blocking audio loop in a thread — don't await, let the event loop breathe
        self._loop.run_in_executor(None, self._listen_sync)

        # Keep the coroutine alive while the thread runs
        while self._running:
            await asyncio.sleep(0.5)

    def stop(self) -> None:
        self._running = False

    def _set_state(self, new_state: State) -> None:
        if self._state != new_state:
            old = self._state
            self._state = new_state
            self._last_state_change = time.time()
            if self._loop and self._on_state_change:
                self._loop.call_soon_threadsafe(
                    self._on_state_change, old, new_state
                )

    def _log(self, msg: str) -> None:
        if self._debug:
            print(f"[listener:{self._state.name}] {msg}")

    # ── SYNC audio loop (runs in thread) ──────────────────────

    def _listen_sync(self) -> None:
        chunk_size = int(self._sr * 0.2)
        audio_buffer: list[np.ndarray] = []
        energy_history: list[float] = []

        with sd.InputStream(
            samplerate=self._sr,
            channels=1,
            dtype="int16",
            device=self._device,
            blocksize=chunk_size,
        ) as stream:
            while self._running:
                data, _ = stream.read(chunk_size)
                energy = float(np.abs(data).mean())
                energy_history.append(energy)
                if len(energy_history) > 25:
                    energy_history.pop(0)

                speaking = energy > self._silence_threshold * 1.5
                now = time.time()

                if self._state == State.IDLE:
                    # Debug: log energy every 2 seconds
                    if self._debug and int(now) % 2 == 0 and int(now) != getattr(self, '_last_log_sec', 0):
                        setattr(self, '_last_log_sec', int(now))
                        avg_e = sum(energy_history[-10:]) / min(len(energy_history), 10) if energy_history else 0
                        mode = "no-wake" if self._no_wake else "wake:" + ",".join(self._wake_words)
                        print(f"[idle] mic={energy:4.0f} avg={avg_e:4.0f} th={self._silence_threshold * 1.5:4.0f} spk={speaking} {mode}", end="\r")

                    if speaking:
                        audio_buffer.append(data.copy())
                        if len(audio_buffer) * 0.2 >= self._wake_chunk_dur:
                            audio = np.concatenate(audio_buffer).flatten()
                            audio_buffer.clear()
                            if self._no_wake:
                                # Skip wake word — go directly to active
                                self._set_state(State.WAKING)
                                self._schedule_async(self._on_wake, "говорите")
                            else:
                                self._check_wake_word_sync(audio)
                    else:
                        audio_buffer.clear()

                elif self._state == State.WAKING:
                    time.sleep(0.1)

                elif self._state == State.ACTIVE:
                    if speaking:
                        self._last_speech_time = now
                        audio_buffer.append(data.copy())
                    else:
                        silence_dur = now - self._last_speech_time
                        if audio_buffer and silence_dur > 1.2 and self._last_speech_time > 0:
                            audio = np.concatenate(audio_buffer).flatten()
                            audio_buffer.clear()
                            self._last_speech_time = 0
                            self._process_command_sync(audio)
                        elif self._last_speech_time == 0 and silence_dur > self._active_timeout:
                            self._set_state(State.COOLDOWN)
                            audio_buffer.clear()

                elif self._state == State.COOLDOWN:
                    if speaking:
                        self._last_speech_time = now
                        audio_buffer.append(data.copy())
                        if len(audio_buffer) * 0.2 >= 1.0:
                            self._set_state(State.ACTIVE)
                    else:
                        cooldown_elapsed = now - self._last_state_change
                        if cooldown_elapsed > self._cooldown_timeout:
                            self._set_state(State.IDLE)
                            audio_buffer.clear()

    # ── Sync helpers (called from thread, schedule async callbacks) ──

    def _check_wake_word_sync(self, audio: np.ndarray) -> None:
        try:
            text = self.stt.transcribe_fast(audio)
            text_lower = text.lower().strip()
            print(f"\n[listener] 🎙 '{text_lower[:60]}'", end="\r")

            if not text_lower or len(text_lower) < 2:
                return

            # Exact match first
            for ww in self._wake_words:
                if ww in text_lower:
                    self._set_state(State.WAKING)
                    self._schedule_async(self._on_wake, text)
                    return

            # Fuzzy: check every 3-gram in text against wake words
            for ww in self._wake_words:
                if len(ww) < 3:
                    continue
                # Sliding window over text
                for i in range(len(text_lower) - len(ww) + 1):
                    window = text_lower[i:i + len(ww)]
                    # Count matching chars
                    same = sum(1 for a, b in zip(window, ww) if a == b)
                    if same >= len(ww) - 1:  # 1 char difference tolerated
                        self._set_state(State.WAKING)
                        self._schedule_async(self._on_wake, text)
                        return

            if self._debug:
                print(f"\n[listener] no wake: '{text_lower[:60]}'")
        except Exception as e:
            self._log(f"wake check error: {e}")

    def _process_command_sync(self, audio: np.ndarray) -> None:
        try:
            text = self.stt.transcribe_array_sync(audio)
            text = text.strip()
            self._log(f"command: '{text}'")
            if len(text) >= 2:
                self._schedule_async(self._on_command, text)
        except Exception as e:
            self._log(f"command error: {e}")

    def _schedule_async(self, callback, *args) -> None:
        """Schedule an async callback on the main event loop from a thread."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(callback(*args), self._loop)

    def confirm_active(self) -> None:
        self._set_state(State.ACTIVE)
        self._last_speech_time = time.time()

    def return_to_idle(self) -> None:
        self._set_state(State.IDLE)
