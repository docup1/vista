from __future__ import annotations

import asyncio
import io
import threading
import wave
from typing import Callable

import numpy as np
import sounddevice as sd

from core.config import Config


def _find_input_device() -> int | None:
    """Find a working microphone — prefer built-in, skip wireless."""
    devices = sd.query_devices()
    # Prefer built-in MacBook mic
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0 and "MacBook" in dev["name"]:
            return i
    # Fallback: any wired mic
    for i, dev in enumerate(devices):
        name = dev["name"]
        if dev["max_input_channels"] > 0 and "AirPods" not in name and "iPhone" not in name:
            return i
    # Last resort
    for i, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            return i
    return None


class STTEngine:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.get_instance()
        self._model = None
        self._sample_rate = self.config.sample_rate
        self._loaded = False
        cfg_device = self.config.get("voice.input_device")
        self._device: int | None = (
            int(cfg_device) if cfg_device is not None else _find_input_device()
        )

    def _load_model(self):
        if self._loaded:
            return
        try:
            from faster_whisper import WhisperModel

            model_size = self.config.stt_model_size
            compute = self.config.get("models.stt.compute_type", "int8")
            self._model = WhisperModel(
                model_size,
                device="cpu",
                compute_type=compute,
                num_workers=2,
            )
            self._loaded = True
        except ImportError:
            raise RuntimeError(
                "faster-whisper not installed. Run: pip install faster-whisper"
            )

    def load(self) -> None:
        """Pre-load model at startup."""
        self._load_model()

    async def transcribe_file(self, audio_path: str) -> str:
        self._load_model()
        segments, _ = self._model.transcribe(
            audio_path,
            language=self.config.stt_language,
            beam_size=1,
        )
        text = " ".join(seg.text for seg in segments)
        return text.strip()

    async def transcribe_array(self, audio: np.ndarray) -> str:
        self._load_model()
        segments, _ = self._model.transcribe(
            audio.astype(np.float32) / 32768.0,
            language=self.config.stt_language,
            beam_size=1,
            vad_filter=True,
        )
        text = " ".join(seg.text for seg in segments)
        return text.strip()

    def transcribe_array_sync(self, audio: np.ndarray) -> str:
        """Synchronous version — for use in background threads."""
        self._load_model()
        segments, _ = self._model.transcribe(
            audio.astype(np.float32) / 32768.0,
            language=self.config.stt_language,
            beam_size=1,
        )
        text = " ".join(seg.text for seg in segments)
        return text.strip()

    def transcribe_fast(self, audio: np.ndarray) -> str:
        """Higher quality for wake word detection."""
        self._load_model()
        segments, _ = self._model.transcribe(
            audio.astype(np.float32) / 32768.0,
            language=self.config.stt_language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                threshold=0.4,
                min_speech_duration_ms=250,
                min_silence_duration_ms=100,
            ),
        )
        text = " ".join(seg.text for seg in segments)
        return text.strip()

    async def listen_and_transcribe(
        self,
        duration: float | None = None,
        on_speech_start: Callable | None = None,
        on_speech_end: Callable | None = None,
    ) -> str:
        sr = self._sample_rate
        loop = asyncio.get_running_loop()

        if duration:
            recording = await loop.run_in_executor(
                None, self._record_fixed, duration, sr
            )
            return await self.transcribe_array(recording.flatten())

        # VAD-like: record until silence
        audio = await loop.run_in_executor(
            None, self._record_vad, sr, on_speech_start, on_speech_end
        )
        if audio is None or len(audio) == 0:
            return ""
        return await self.transcribe_array(audio)

    def _record_fixed(self, duration: float, sr: int) -> np.ndarray:
        recording = sd.rec(
            int(duration * sr),
            samplerate=sr,
            channels=1,
            dtype="int16",
            device=self._device,
            blocking=True,
        )
        return recording

    def _record_vad(
        self,
        sr: int,
        on_speech_start: Callable | None,
        on_speech_end: Callable | None,
    ) -> np.ndarray | None:
        chunk_duration = 0.3
        silence_threshold = self.config.get("voice.silence_threshold", 300)
        silence_dur = self.config.get("voice.silence_duration", 1.0)
        max_dur = self.config.get("voice.max_record_duration", 15.0)

        chunks = []
        silent_chunks = 0
        max_silent = int(silence_dur / chunk_duration)
        speaking = False

        with sd.InputStream(
            samplerate=sr,
            channels=1,
            dtype="int16",
            device=self._device,
            blocksize=int(sr * chunk_duration),
        ) as stream:
            total_chunks = int(max_dur / chunk_duration)
            for i in range(total_chunks):
                data, _ = stream.read(int(sr * chunk_duration))
                amplitude = float(np.abs(data).mean())

                if amplitude > silence_threshold:
                    if not speaking:
                        speaking = True
                        if on_speech_start:
                            on_speech_start()
                    silent_chunks = 0
                elif speaking:
                    silent_chunks += 1

                if speaking:
                    chunks.append(data.copy())

                if speaking and silent_chunks >= max_silent:
                    break

        if not chunks:
            return None

        if on_speech_end:
            on_speech_end()

        return np.concatenate(chunks).flatten()
