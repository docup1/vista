    from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path


class ScreenshotCapture:
    async def capture(self, output_path: str | None = None) -> str:
        if output_path is None:
            output_path = tempfile.mktemp(suffix=".png")
        proc = await asyncio.create_subprocess_exec(
            "screencapture", "-x", output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return output_path

    async def capture_and_describe(self, llm_client) -> str:
        path = await self.capture()
        return f"Screenshot saved to {path}"
