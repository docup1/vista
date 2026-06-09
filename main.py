#!/usr/bin/env python3
"""Vista — Локальный AI-ассистент, аналог Джарвиса."""

from __future__ import annotations

import argparse
import asyncio
import sys

from core.orchestrator import Orchestrator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vista — локальный AI-ассистент (аналог Джарвиса)",
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["cli", "voice", "daemon", "once"],
        default="cli",
        help="Режим: cli (текст), voice (голос), daemon (фон + wake word), once (один запрос)",
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Путь к конфигурационному файлу",
    )
    parser.add_argument(
        "-q", "--query",
        default=None,
        help="Один запрос (режим once)",
    )
    return parser.parse_args()


async def main_async() -> None:
    args = parse_args()

    orchestrator = Orchestrator()
    orchestrator.setup(mode=args.mode)

    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        await orchestrator.shutdown()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
