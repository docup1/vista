#!/usr/bin/env python3
"""Test and compare TTS voices — Piper (neural) vs macOS say."""

import subprocess
import sys
import io
import wave
from pathlib import Path

PHRASE = "Привет! Я Vista, твой локальный AI-ассистент. Теперь у меня приятный и естественный голос."


def test_macos(voice: str, rate: int = 190):
    print(f"\n🎤 macOS say — {voice} (rate={rate})")
    print(f"   {PHRASE}")
    subprocess.run(["say", "-v", voice, "-r", str(rate), PHRASE], timeout=30)


def test_piper(model_name: str = "ru_RU-ruslan-medium"):
    try:
        from piper import PiperVoice
    except ImportError:
        print("Piper not installed: pip install piper-tts")
        return

    model_dir = Path("./data/piper")
    model_file = model_dir / f"{model_name}.onnx"
    if not model_file.exists():
        print(f"Model not found: {model_file}")
        print("Download:")
        print(f"  mkdir -p data/piper && cd data/piper")
        print(f"  curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/ruslan/medium/{model_name}.onnx")
        print(f"  curl -LO https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/ruslan/medium/{model_name}.onnx.json")
        return

    print(f"\n🎤 Piper (нейросетевой) — {model_name}")
    print(f"   {PHRASE}")

    voice = PiperVoice.load(str(model_file))

    buf = io.BytesIO()
    with wave.open(buf, "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(voice.config.sample_rate)
        voice.synthesize_wav(PHRASE, wav_file)

    audio = buf.getvalue()
    proc = subprocess.Popen(
        ["afplay", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.communicate(input=audio)


def main():
    print("=" * 55)
    print("  Vista — сравнение голосов")
    print("=" * 55)

    # Piper (neural)
    test_piper()

    # macOS voices
    for v in ["Katya", "Milena", "Yuri"]:
        test_macos(v)

    print("\n" + "=" * 55)
    print("  Итог:")
    print("  Piper — нейросетевой, самый естественный ✅")
    print("  Katya — лучший из системных")
    print("  Milena — стандартный")
    print("  Yuri — мужской")
    print()
    print("  Выбрать в config.yaml: models.tts.engine = piper")
    print("=" * 55)


if __name__ == "__main__":
    main()
