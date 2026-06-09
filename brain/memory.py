from __future__ import annotations

import hashlib
import time
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from core.config import Config


class Memory:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.get_instance()
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None
        self._conversation_history: list[dict[str, str]] = []

    def _ensure_initialized(self):
        if self._client is None:
            persist_dir = self.config.memory_persist_dir
            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            collection_name = self.config.memory_collection
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )

    def add_conversation_turn(self, role: str, content: str) -> None:
        self._conversation_history.append({"role": role, "content": content})

        # Only persist to vector DB if meaningful (not empty, not too short)
        if len(content.strip()) < 5:
            return
        self._ensure_initialized()
        msg_id = hashlib.md5(f"{role}:{content}:{time.time()}".encode()).hexdigest()
        self._collection.add(
            ids=[msg_id],
            documents=[f"{role}: {content}"],
            metadatas=[{"role": role, "timestamp": time.time()}],
        )

    def get_context_messages(self, query: str | None = None, n: int | None = None) -> list[dict[str, str]]:
        n = n or self.config.max_context_messages

        # If history is long, use hybrid: recent + RAG-relevant
        threshold = self.config.summarize_threshold
        if len(self._conversation_history) > threshold and query:
            relevant = self._search_relevant(query, n // 2)
            recent = self._conversation_history[-(n // 2):]
            seen = {m["content"] for m in relevant}
            for msg in reversed(recent):
                if msg["content"] not in seen:
                    relevant.insert(0, msg)
                    seen.add(msg["content"])
            return relevant[-n:]

        return self._conversation_history[-n:] if n > 0 else self._conversation_history

    def _search_relevant(self, query: str, n: int) -> list[dict[str, str]]:
        # Skip vector search for very short queries — just return recent
        if len(query.strip()) < 5:
            return self._conversation_history[-n:]
        self._ensure_initialized()
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(n, self._collection.count()),
            )
            ids = results.get("ids", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            docs = results.get("documents", [[]])[0]

            relevant: list[dict[str, str]] = []
            for doc_id, meta, doc in zip(ids, metadatas, docs):
                role = meta.get("role", "user") if meta else "user"
                content = doc.split(": ", 1)[1] if ": " in doc else doc
                relevant.append({"role": role, "content": content})

            recent = self._conversation_history[-n:]
            seen = {msg["content"] for msg in relevant}
            for msg in reversed(recent):
                if msg["content"] not in seen:
                    relevant.insert(0, msg)
                    seen.add(msg["content"])
                    if len(relevant) >= n:
                        break
            return relevant[-n:]
        except Exception:
            return self._conversation_history[-n:]

    def clear_history(self) -> None:
        self._conversation_history.clear()

    def get_history(self) -> list[dict[str, str]]:
        return list(self._conversation_history)

    def count(self) -> int:
        self._ensure_initialized()
        return self._collection.count()

    def summarize_and_compact(self) -> str | None:
        if len(self._conversation_history) < 10:
            return None
        parts = []
        for msg in self._conversation_history:
            content = msg["content"]
            if len(content) > 200:
                content = content[:200] + "..."
            parts.append(f"[{msg['role']}]: {content}")
        return " | ".join(parts)
