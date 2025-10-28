from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping

LOG_PATH = Path("data/logs/queries.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
MAX_LOG_BYTES = 10 * 1024 * 1024

_log_lock = threading.Lock()


def _rotate_log_if_needed(path: Path) -> None:
    if not path.exists():
        return
    if path.stat().st_size <= MAX_LOG_BYTES:
        return
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    rotated = path.with_name(f"{path.stem}-{timestamp}{path.suffix}")
    path.rename(rotated)


def log_query(
    *,
    engine: str,
    rows: int,
    latency_ms: float,
    models: Iterable[str],
    sql: str,
    question: str,
    bq_est_bytes: int | None = None,
    cache_hit: bool | None = None,
    path: Path = LOG_PATH,
) -> None:
    record: dict[str, Any] = {
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "engine": engine,
        "rows": rows,
        "latency_ms": round(latency_ms, 2),
        "model_names": sorted(set(models)),
        "sql_hash": sha256(sql.encode("utf-8")).hexdigest(),
        "question_hash": sha256(question.encode("utf-8")).hexdigest(),
    }
    if bq_est_bytes is not None:
        record["bq_est_bytes"] = bq_est_bytes
    if cache_hit is not None:
        record["cache_hit"] = cache_hit

    with _log_lock:
        _rotate_log_if_needed(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":")) + os.linesep)


@dataclass(slots=True)
class CacheEntry:
    value: Any
    expires_at: float


class QueryCache:
    def __init__(self, ttl_seconds: int = 180) -> None:
        self.ttl = ttl_seconds
        self._store: dict[str, CacheEntry] = {}
        self._order: deque[str] = deque()
        self._lock = threading.Lock()

    def _make_key(self, engine: str, sql: str) -> str:
        normalized = " ".join(sql.split())
        digest = sha256(normalized.encode("utf-8")).hexdigest()
        return f"{engine}:{digest}"

    def get(self, engine: str, sql: str) -> Any | None:
        key = self._make_key(engine, sql)
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            if entry.expires_at < now:
                del self._store[key]
                return None
            return entry.value

    def set(self, engine: str, sql: str, value: Any) -> None:
        key = self._make_key(engine, sql)
        expires_at = time.monotonic() + self.ttl
        entry = CacheEntry(value=value, expires_at=expires_at)
        with self._lock:
            self._store[key] = entry
            self._order.append(key)
            self._evict_expired()

    def _evict_expired(self) -> None:
        now = time.monotonic()
        while self._order:
            key = self._order[0]
            entry = self._store.get(key)
            if not entry or entry.expires_at < now:
                self._order.popleft()
                self._store.pop(key, None)
            else:
                break


query_cache = QueryCache()


class PromptCache:
    def __init__(self, ttl_seconds: int = 900) -> None:
        self.ttl = ttl_seconds
        self._store: dict[str, CacheEntry] = {}
        self._order: deque[str] = deque()
        self._lock = threading.Lock()

    def _canonicalize_filters(self, filters: Mapping[str, Any] | None) -> Mapping[str, Any]:
        if not filters:
            return {}
        canonical: dict[str, Any] = {}
        sequence_types = list | tuple | set
        for key, value in filters.items():
            if isinstance(value, sequence_types):
                canonical[key] = sorted(value)
            else:
                canonical[key] = value
        return canonical

    def _make_key(
        self,
        provider: str,
        engine: str,
        question: str,
        filters: Mapping[str, Any] | None,
    ) -> str:
        normalized_question = " ".join((question or "").split()).strip().lower()
        canonical_filters = self._canonicalize_filters(filters)
        filters_payload = json.dumps(canonical_filters, sort_keys=True, default=str)
        payload = f"{provider}:{engine}:{normalized_question}:{filters_payload}"
        digest = sha256(payload.encode("utf-8")).hexdigest()
        return digest

    def get(
        self,
        provider: str,
        engine: str,
        question: str,
        filters: Mapping[str, Any] | None,
    ) -> Any | None:
        key = self._make_key(provider, engine, question, filters)
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            if entry.expires_at < now:
                del self._store[key]
                return None
            return entry.value

    def set(
        self,
        provider: str,
        engine: str,
        question: str,
        filters: Mapping[str, Any] | None,
        value: Any,
    ) -> None:
        key = self._make_key(provider, engine, question, filters)
        expires_at = time.monotonic() + self.ttl
        entry = CacheEntry(value=value, expires_at=expires_at)
        with self._lock:
            self._store[key] = entry
            self._order.append(key)
            self._evict_expired()

    def _evict_expired(self) -> None:
        now = time.monotonic()
        while self._order:
            key = self._order[0]
            entry = self._store.get(key)
            if not entry or entry.expires_at < now:
                self._order.popleft()
                self._store.pop(key, None)
            else:
                break


prompt_cache = PromptCache()
