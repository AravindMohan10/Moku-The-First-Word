"""Per-creature memory — Mem0 platform/OSS when available, SQLite keyword fallback."""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Protocol

_WORD = re.compile(r"[a-z0-9]+")


def creature_namespace(world_id: str, creature_id: str) -> str:
    return f"world:{world_id}:creature:{creature_id}"


class MemoryBackend(Protocol):
    def add_memory(
        self,
        world_id: str,
        creature_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    def search_memory(
        self,
        world_id: str,
        creature_id: str,
        query: str,
        k: int = 5,
    ) -> list[str]: ...

    def clear_world(self, world_id: str) -> None: ...


class LocalMemoryStore:
    """SQLite + keyword scoring — no cloud deps."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS creature_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    world_id TEXT NOT NULL,
                    creature_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    metadata TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_creature_mem "
                "ON creature_memories(world_id, creature_id, created_at DESC)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _score(query: str, text: str) -> float:
        q = set(_WORD.findall(query.lower()))
        t = set(_WORD.findall(text.lower()))
        if not q:
            return 0.0
        overlap = len(q & t)
        return overlap / len(q) + overlap * 0.05

    def add_memory(
        self,
        world_id: str,
        creature_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not text.strip():
            return
        meta = "" if not metadata else str(metadata)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO creature_memories(world_id, creature_id, text, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (world_id, creature_id, text.strip()[:500], meta, time.time()),
            )

    def search_memory(
        self,
        world_id: str,
        creature_id: str,
        query: str,
        k: int = 5,
    ) -> list[str]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT text FROM creature_memories "
                "WHERE world_id = ? AND creature_id = ? "
                "ORDER BY created_at DESC LIMIT 80",
                (world_id, creature_id),
            ).fetchall()
        if not rows:
            return []
        scored = sorted(
            ((self._score(query, row["text"]), row["text"]) for row in rows),
            key=lambda item: item[0],
            reverse=True,
        )
        seen: set[str] = set()
        out: list[str] = []
        for _, text in scored:
            if text in seen:
                continue
            seen.add(text)
            out.append(text)
            if len(out) >= k:
                break
        return out

    def clear_world(self, world_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM creature_memories WHERE world_id = ?", (world_id,))


class Mem0MemoryStore:
    """Mem0 platform or OSS backend."""

    def __init__(self) -> None:
        self._client: Any = None
        self._mode = "none"
        api_key = os.environ.get("MEM0_API_KEY", "").strip()
        if api_key:
            try:
                from mem0 import MemoryClient

                self._client = MemoryClient(api_key=api_key)
                self._mode = "platform"
            except Exception:
                self._client = None
                self._mode = "none"
            return
        if os.environ.get("MOKU_MEM0_OSS", "").strip().lower() in {"1", "true", "yes"}:
            try:
                from mem0 import Memory

                self._client = Memory()
                self._mode = "oss"
            except Exception:
                self._client = None
                self._mode = "none"

    @property
    def available(self) -> bool:
        return self._client is not None

    def _user_id(self, world_id: str, creature_id: str) -> str:
        return creature_namespace(world_id, creature_id)

    def add_memory(
        self,
        world_id: str,
        creature_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._client or not text.strip():
            return
        user_id = self._user_id(world_id, creature_id)
        meta = {"world_id": world_id, "creature_id": creature_id, **(metadata or {})}
        try:
            if self._mode == "platform":
                self._client.add(text.strip(), user_id=user_id, metadata=meta, infer=False)
            else:
                self._client.add(
                    [{"role": "user", "content": text.strip()}],
                    user_id=user_id,
                    metadata=meta,
                    infer=False,
                )
        except Exception:
            return

    def search_memory(
        self,
        world_id: str,
        creature_id: str,
        query: str,
        k: int = 5,
    ) -> list[str]:
        if not self._client:
            return []
        user_id = self._user_id(world_id, creature_id)
        try:
            if self._mode == "platform":
                raw = self._client.search(query, filters={"user_id": user_id}, limit=k)
            else:
                raw = self._client.search(query, user_id=user_id, limit=k)
        except Exception:
            return []
        return _extract_mem0_results(raw, k)

    def clear_world(self, world_id: str) -> None:
        if not self._client or self._mode != "platform":
            return
        try:
            prefix = f"world:{world_id}:"
            memories = self._client.get_all(filters={"user_id": {"contains": prefix}})
            for item in _extract_mem0_items(memories):
                mem_id = item.get("id")
                if mem_id:
                    self._client.delete(mem_id)
        except Exception:
            return


def _extract_mem0_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        items = raw.get("results") or raw.get("memories") or raw.get("data") or []
        return list(items) if isinstance(items, list) else []
    if isinstance(raw, list):
        return raw
    return []


def _extract_mem0_results(raw: Any, k: int) -> list[str]:
    out: list[str] = []
    for item in _extract_mem0_items(raw):
        text = item.get("memory") or item.get("text") or item.get("content")
        if isinstance(text, str) and text.strip():
            out.append(text.strip())
        if len(out) >= k:
            break
    return out


class HybridMemoryStore:
    """Mem0 when configured; always mirror to local store for reliability."""

    def __init__(self) -> None:
        db_path = Path(os.environ.get("MOKU_MEMORY_DB", "data/moku_memories.sqlite3"))
        self._local = LocalMemoryStore(db_path)
        self._mem0 = Mem0MemoryStore()

    @property
    def backend_label(self) -> str:
        mode = os.environ.get("MOKU_MEM0_RETRIEVE", "auto").strip().lower()
        if self._mem0.available:
            if mode == "local":
                return "mem0 (platform writes) + local retrieve"
            return f"mem0 ({self._mem0._mode}) + local mirror"
        return "local sqlite"

    def add_memory(
        self,
        world_id: str,
        creature_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._local.add_memory(world_id, creature_id, text, metadata)
        self._mem0.add_memory(world_id, creature_id, text, metadata)

    def search_memory(
        self,
        world_id: str,
        creature_id: str,
        query: str,
        k: int = 5,
    ) -> list[str]:
        mode = os.environ.get("MOKU_MEM0_RETRIEVE", "auto").strip().lower()
        if mode == "local":
            return self._local.search_memory(world_id, creature_id, query, k=k)
        if mode == "platform" and self._mem0.available:
            hits = self._mem0.search_memory(world_id, creature_id, query, k=k)
            if hits:
                return hits
            return self._local.search_memory(world_id, creature_id, query, k=k)
        if self._mem0.available:
            hits = self._mem0.search_memory(world_id, creature_id, query, k=k)
            if hits:
                return hits
        return self._local.search_memory(world_id, creature_id, query, k=k)

    def clear_world(self, world_id: str) -> None:
        self._local.clear_world(world_id)
        self._mem0.clear_world(world_id)


_STORE: HybridMemoryStore | None = None


def get_memory_store() -> HybridMemoryStore:
    global _STORE
    if _STORE is None:
        _STORE = HybridMemoryStore()
    return _STORE
