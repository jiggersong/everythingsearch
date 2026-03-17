import hashlib
import json
import sqlite3
import threading
from typing import Any

from pydantic import ConfigDict
from langchain_community.embeddings import DashScopeEmbeddings


class EmbeddingCache:
    """Thread-safe SQLite cache for embedding vectors."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS embeddings "
            "(text_hash TEXT PRIMARY KEY, vector TEXT)"
        )
        conn.commit()

    @staticmethod
    def _hash(model: str, text: str) -> str:
        return hashlib.sha256(f"{model}::{text}".encode("utf-8")).hexdigest()

    def get_many(self, model: str, texts: list[str]) -> dict[str, list[float] | None]:
        hashes = {self._hash(model, t): t for t in texts}
        result: dict[str, list[float] | None] = {t: None for t in texts}

        conn = self._get_conn()
        hash_list = list(hashes.keys())
        for i in range(0, len(hash_list), 500):
            batch = hash_list[i:i + 500]
            placeholders = ",".join("?" * len(batch))
            rows = conn.execute(
                f"SELECT text_hash, vector FROM embeddings WHERE text_hash IN ({placeholders})",
                batch,
            ).fetchall()
            for h, vec_json in rows:
                text = hashes[h]
                result[text] = json.loads(vec_json)
        return result

    def put_many(self, model: str, items: list[tuple[str, list[float]]]):
        conn = self._get_conn()
        rows = [(self._hash(model, text), json.dumps(vec)) for text, vec in items]
        conn.executemany(
            "INSERT OR REPLACE INTO embeddings (text_hash, vector) VALUES (?, ?)",
            rows,
        )
        conn.commit()


class CachedEmbeddings(DashScopeEmbeddings):
    """DashScopeEmbeddings with a transparent SQLite cache layer."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _cache: Any = None
    cache_hits: int = 0
    api_calls: int = 0

    def __init__(self, cache_path: str = "./embedding_cache.db", **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, "_cache", EmbeddingCache(cache_path))

    # DashScope 单行最大 2048 Token，混合文本保守截断
    _EMBED_MAX = 600

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        safe_texts = []
        for t in texts:
            if not t or not t.strip():
                safe_texts.append(" ")
            elif len(t) > self._EMBED_MAX:
                safe_texts.append(t[: self._EMBED_MAX])
            else:
                safe_texts.append(t)
        cached = self._cache.get_many(self.model, safe_texts)

        uncached_indices = []
        for i, t in enumerate(safe_texts):
            if cached[t] is None:
                uncached_indices.append(i)

        self.cache_hits += len(safe_texts) - len(uncached_indices)
        self.api_calls += len(uncached_indices)

        if uncached_indices:
            uncached_texts = [safe_texts[i] for i in uncached_indices]
            new_vectors = super().embed_documents(uncached_texts)
            to_cache = []
            for idx, vec in zip(uncached_indices, new_vectors):
                cached[safe_texts[idx]] = vec
                to_cache.append((safe_texts[idx], vec))
            self._cache.put_many(self.model, to_cache)

        return [cached[t] for t in safe_texts]

    def embed_query(self, text: str) -> list[float]:
        safe = (text[: self._EMBED_MAX] if text and len(text) > self._EMBED_MAX else text) or " "
        result = self._cache.get_many(self.model, [safe])
        if result[safe] is not None:
            self.cache_hits += 1
            return result[safe]
        self.api_calls += 1
        vec = super().embed_query(safe)
        self._cache.put_many(self.model, [(safe, vec)])
        return vec

    def stats_str(self) -> str:
        total = self.cache_hits + self.api_calls
        if total == 0:
            return "无嵌入调用"
        return f"API 调用: {self.api_calls} / {total} ({self.cache_hits} 缓存命中)"
