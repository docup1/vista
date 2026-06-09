from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator

import httpx

from core.config import Config


class LLMClient:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.get_instance()
        self.host = self.config.llm_host
        self.model = self.config.llm_model
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        return self._client

    async def check_connection(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get(f"{self.host}/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        client = await self._get_client()
        resp = await client.get(f"{self.host}/api/tags")
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]

    async def pull_model(self, model: str | None = None) -> None:
        model = model or self.model
        client = await self._get_client()
        async with client.stream(
            "POST",
            f"{self.host}/api/pull",
            json={"name": model, "stream": True},
        ) as response:
            async for line in response.aiter_lines():
                if line.strip():
                    try:
                        data = json.loads(line)
                        status = data.get("status", "")
                        if "progress" in data:
                            pct = data.get("completed", 0) / data.get("total", 1) * 100
                            print(f"\r  Pulling {model}: {status} {pct:.0f}%", end="")
                    except json.JSONDecodeError:
                        pass
        print()

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        client = await self._get_client()
        embeddings = []
        for text in texts:
            resp = await client.post(
                f"{self.host}/api/embeddings",
                json={"model": self.config.embeddings_model, "prompt": text},
            )
            data = resp.json()
            embeddings.append(data.get("embedding", []))
        return embeddings

    async def chat(
        self,
        messages: list[dict[str, str]],
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        client = await self._get_client()

        # Sanitize messages — remove surrogates that break JSON
        safe_messages = []
        for m in messages:
            safe_messages.append({
                "role": m["role"],
                "content": m["content"].encode("utf-8", errors="replace").decode("utf-8", errors="replace"),
            })

        payload = {
            "model": self.model,
            "messages": safe_messages,
            "stream": stream,
            "keep_alive": self.config.get("models.llm.keep_alive", -1),
            "options": {
                "temperature": self.config.llm_temperature,
                "num_predict": self.config.llm_max_tokens,
                "num_thread": self.config.get("models.llm.num_thread", 8),
                "stop": self.config.llm_stop_tokens,
            },
        }

        if stream:
            return self._stream_chat(client, payload)
        else:
            resp = await client.post(f"{self.host}/api/chat", json=payload)
            data = resp.json()
            return data.get("message", {}).get("content", "")

    async def _stream_chat(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
    ) -> AsyncIterator[str]:
        async with client.stream(
            "POST", f"{self.host}/api/chat", json=payload
        ) as response:
            async for line in response.aiter_lines():
                if line.strip():
                    try:
                        data = json.loads(line)
                        if data.get("done"):
                            break
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


def parse_function_call(text: str) -> tuple[str | None, dict[str, Any] | None]:
    # Try JSON format: {"function": "name", "parameters": {...}}
    json_match = re.search(
        r'\{\s*"function"\s*:\s*"([^"]+)"\s*,\s*"parameters"\s*:\s*(\{[^}]*\})\s*\}',
        text,
    )
    if json_match:
        try:
            func_name = json_match.group(1)
            params = json.loads(json_match.group(2))
            return func_name, params
        except json.JSONDecodeError:
            pass

    # Try code block with JSON
    json_match = re.search(r'```(?:json)?\s*\n?(\{.*?"function".*?\})\s*```', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return data.get("function"), data.get("parameters", {})
        except json.JSONDecodeError:
            pass

    # Try bracket notation: [function_name(param=value)]
    bracket_match = re.findall(r'\[(\w+)\(([^)]*)\)\]', text)
    if bracket_match:
        func_name = bracket_match[0][0]
        args_str = bracket_match[0][1]
        params = {}
        if args_str:
            for arg in args_str.split(","):
                arg = arg.strip()
                if "=" in arg:
                    k, v = arg.split("=", 1)
                    params[k.strip()] = v.strip().strip("'\"")
                else:
                    params["value"] = arg
        return func_name, params

    # Try agent: format — agent:function_name args
    agent_match = re.search(r'\nagent:\s*(\w+)\s*(.*?)(?:\n|$)', text, re.IGNORECASE)
    if agent_match:
        func_name = agent_match.group(1)
        args = agent_match.group(2).strip().strip("'\"")
        params = {}
        if args:
            params["value"] = args
        return func_name, params

    # Try CALL with or without colon — CALL: func() or CALL func()
    call_match = re.search(r'CALL:?\s*(\w+)\(([^)]*)\)', text, re.IGNORECASE)
    if call_match:
        func_name = call_match.group(1)
        args_str = call_match.group(2).strip().strip("{}").strip()
        params = {}
        if args_str and args_str not in ("", "{}"):
            for part in args_str.split(","):
                part = part.strip()
                if not part:
                    continue
                if "=" in part:
                    k, v = part.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if v and v not in ("", "{}"):
                        params[k] = v
                elif part:
                    val = part.strip().strip("'\"")
                    if val:
                        params["value"] = val
        return func_name, params

    # Try plain function call: function_name(key=value) or function_name(value)
    call_match = re.findall(
        r'(get_time|get_date|launch_app|run_shell|read_file|write_file|'
        r'system_info|open_url|git_status|git_diff|git_log|calculate)\(([^)]*)\)',
        text,
        re.IGNORECASE,
    )
    if call_match:
        func_name = call_match[0][0]
        args = call_match[0][1].strip().strip("'\"")
        params = {}
        if args:
            if "=" in args and not args.startswith("="):
                for part in args.split(","):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        params[k.strip()] = v.strip().strip("'\"")
                    elif part:
                        params["value"] = part.strip().strip("'\"")
            else:
                params["value"] = args
        return func_name, params

    return None, None
