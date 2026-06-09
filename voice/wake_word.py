from __future__ import annotations

import asyncio
from collections import deque
from typing import Callable

import numpy as np
import sounddevice as sd

from core.config import Config


class WakeWordDetector:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.get_instance()
        self._wake_words = self.config.wake_words
        self._sample_rate = self.config.sample_rate
        self._detector = None
        self._running = False
        self._on_detected: Callable | None = None

    def _init_detector(self):
        try:
            from openwakeword import Model as OWWModel
            self._detector = OWWModel(wakeword_models=["alexa"], inference_framework="onnx")
        except ImportError:
            pass

    async def listen(
        self,
        on_detected: Callable,
        on_listening: Callable | None = None,
    ) -> None:
        self._running = True
        self._on_detected = on_detected

        await self._mic_wake_loop(on_detected, on_listening)

    async def _mic_wake_loop(self, on_detected, on_listening):
        chunk_duration = 0.1
        sr = self._sample_rate
        chunk_size = int(sr * chunk_duration)
        audio_buffer = deque(maxlen=int(2.0 / chunk_duration))

        # Fallback: energy-based detection with keyword spotting via STT
        energy_threshold = 300
        recording = False
        record_buffer = []
        silence_count = 0
        max_record = int(3.0 / chunk_duration)
        max_silence = int(1.0 / chunk_duration)

        with sd.InputStream(
            samplerate=sr,
            channels=1,
            dtype="int16",
            blocksize=chunk_size,
        ) as stream:
            while self._running:
                data, _ = stream.read(chunk_size)
                energy = np.abs(data).mean()

                if on_listening:
                    on_listening(energy)

                if energy > energy_threshold and not recording:
                    recording = True
                    record_buffer = [data.copy()]
                    silence_count = 0
                elif recording:
                    record_buffer.append(data.copy())
                    if energy < energy_threshold / 2:
                        silence_count += 1
                    else:
                        silence_count = 0

                    if silence_count >= max_silence:
                        recording = False
                        audio = np.concatenate(record_buffer).flatten()
                        await on_detected(audio)
                        record_buffer = []
                    elif len(record_buffer) >= max_record:
                        recording = False
                        audio = np.concatenate(record_buffer).flatten()
                        await on_detected(audio)
                        record_buffer = []

                await asyncio.sleep(0.01)

    def stop(self):
        self._running = False
