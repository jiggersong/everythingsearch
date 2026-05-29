import hashlib
import json
import logging
import sqlite3
import threading
import time
from array import array
from dataclasses import dataclass
from typing import Any
from queue import Queue, Empty

from pydantic import ConfigDict, PrivateAttr
from langchain_community.embeddings import DashScopeEmbeddings

from everythingsearch.infra.dashscope_embed_client import (
    DASHSCOPE_TEXT_EMBEDDING_MAINLAND_LIMITS,
    call_with_retry,
)
from everythingsearch.infra.embed_rate_limiter import (
    DualTokenBucketRateLimiter,
    estimate_tokens_for_texts,
)

logger = logging.getLogger(__name__)

# 与 DashScope SDK / langchain 单批上限一致
DASHSCOPE_EMBED_BATCH_SIZES: dict[str, int] = {
    name: limits.api_batch_size for name, limits in DASHSCOPE_TEXT_EMBEDDING_MAINLAND_LIMITS.items()
}


@dataclass(frozen=True)
class EmbeddingStatsSnapshot:
    """embedding 缓存与远端调用统计快照。"""

    cache_hit_text_count: int
    uncached_text_count: int
    remote_batch_count: int


class ConnectionPool:
    """SQLite 连接池实现"""

    def __init__(self, db_path: str, max_connections: int = 5, timeout: int = 30):
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout
        self._pool = Queue(max_connections)
        self._created_connections = 0
        self._lock = threading.Lock()
        self._initialized = False

    def _create_connection(self) -> sqlite3.Connection:
        """创建新连接并启用 WAL 模式"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=self.timeout)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.commit()
        return conn

    def initialize(self):
        """初始化连接池"""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            for _ in range(self.max_connections):
                conn = self._create_connection()
                self._pool.put(conn)
            self._created_connections = self.max_connections
            self._initialized = True

    def get_connection(self, timeout: float = 10.0) -> sqlite3.Connection:
        """从连接池获取连接"""
        self.initialize()
        try:
            return self._pool.get(timeout=timeout)
        except Empty:
            logger.warning("连接池耗尽，创建临时连接")
            return self._create_connection()

    def return_connection(self, conn: sqlite3.Connection):
        """归还连接到池"""
        try:
            conn.execute("SELECT 1")
            self._pool.put(conn, block=False)
        except (sqlite3.Error, Exception):
            try:
                conn.close()
            except Exception:
                pass

    def close_all(self):
        """关闭所有连接"""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Exception:
                pass


class EmbeddingCache:
    """Thread-safe SQLite cache for embedding vectors with connection pool."""

    def __init__(self, db_path: str, max_connections: int = 5, *, storage_format: str = "blob_float32"):
        if storage_format != "blob_float32":
            raise ValueError(f"不支持的向量缓存格式: {storage_format}（当前仅 blob_float32）")
        self.db_path = db_path
        self._storage_format = storage_format
        self._pool = ConnectionPool(db_path, max_connections)
        self._init_db()

    def _init_db(self):
        """初始化数据库表；兼容旧版 TEXT 向量缓存并迁移至 BLOB 列。"""
        conn = self._pool.get_connection()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS embeddings "
                "(text_hash TEXT PRIMARY KEY, vector TEXT, vector_blob BLOB, created_at REAL)"
            )
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'"
            ).fetchone()
            if row:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(embeddings)").fetchall()}
                if "vector_blob" not in cols:
                    conn.execute("ALTER TABLE embeddings ADD COLUMN vector_blob BLOB")
                if "created_at" not in cols:
                    conn.execute("ALTER TABLE embeddings ADD COLUMN created_at REAL")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_created_at ON embeddings(created_at)"
            )
            conn.commit()
        finally:
            self._pool.return_connection(conn)

    @staticmethod
    def _hash(cache_key: str, text: str) -> str:
        return hashlib.sha256(f"{cache_key}::{text}".encode("utf-8")).hexdigest()

    def _vector_to_blob(self, vector: list[float]) -> bytes:
        arr = array("f", vector)
        return arr.tobytes()

    def _blob_to_vector(self, blob: bytes) -> list[float]:
        arr = array("f")
        arr.frombytes(blob)
        return arr.tolist()

    def get_many(self, cache_key: str, texts: list[str]) -> dict[str, list[float] | None]:
        hashes = {self._hash(cache_key, t): t for t in texts}
        result: dict[str, list[float] | None] = {t: None for t in texts}

        conn = self._pool.get_connection()
        try:
            hash_list = list(hashes.keys())
            for i in range(0, len(hash_list), 500):
                batch = hash_list[i : i + 500]
                placeholders = ",".join("?" * len(batch))
                rows = conn.execute(
                    f"SELECT text_hash, vector_blob, vector FROM embeddings WHERE text_hash IN ({placeholders})",
                    batch,
                ).fetchall()
                for h, vec_blob, vec_json in rows:
                    text = hashes[h]
                    if vec_blob is not None:
                        result[text] = self._blob_to_vector(vec_blob)
                    elif vec_json is not None:
                        result[text] = json.loads(vec_json)
        finally:
            self._pool.return_connection(conn)
        return result

    def put_many(self, cache_key: str, items: list[tuple[str, list[float]]]):
        """批量写入缓存，使用 BLOB 存储向量以减少磁盘占用。"""
        now = time.time()
        conn = self._pool.get_connection()
        try:
            rows = [
                (
                    self._hash(cache_key, text),
                    None,
                    self._vector_to_blob(vec),
                    now,
                )
                for text, vec in items
            ]
            conn.executemany(
                "INSERT OR REPLACE INTO embeddings (text_hash, vector, vector_blob, created_at) VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.commit()
        finally:
            self._pool.return_connection(conn)

    def cleanup_old_entries(self, max_age_days: int = 30):
        """清理过期缓存条目"""
        cutoff = time.time() - (max_age_days * 24 * 3600)
        conn = self._pool.get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM embeddings WHERE created_at IS NOT NULL AND created_at < ?",
                (cutoff,),
            )
            conn.commit()
            deleted = cursor.rowcount
            if deleted > 0:
                conn.execute("VACUUM")
            return deleted
        finally:
            self._pool.return_connection(conn)


class CachedEmbeddings(DashScopeEmbeddings):
    """DashScopeEmbeddings with SQLite cache, rate limiting, and v4 parameters."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _cache: Any = None
    _base_cache_key: str = ""
    _document_cache_key: str = ""
    _query_cache_key: str = ""
    _rate_limiter: DualTokenBucketRateLimiter | None = None
    _embedding_dimensions: int | None = None
    _document_text_type: str = "document"
    _query_text_type: str = "query"
    _embed_max_chars: int = 600
    _embed_retry_max: int = 5
    _embed_backoff_base_ms: int = 500
    _embed_backoff_max_ms: int = 15000
    cache_hits: int = 0
    api_calls: int = 0
    remote_batch_count: int = 0
    _stats_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def __init__(
        self,
        cache_path: str,
        *,
        embed_max_chars: int = 600,
        embedding_dimensions: int | None = None,
        document_text_type: str = "document",
        query_text_type: str = "query",
        vector_storage_format: str = "blob_float32",
        rate_limiter: DualTokenBucketRateLimiter | None = None,
        embed_retry_max: int = 5,
        embed_backoff_base_ms: int = 500,
        embed_backoff_max_ms: int = 15000,
        **kwargs,
    ):
        if not cache_path or not str(cache_path).strip():
            raise ValueError("CachedEmbeddings 需要 cache_path（请传入 config.EMBEDDING_CACHE_PATH）")
        super().__init__(**kwargs)
        model = kwargs.get("model") or getattr(self, "model", "text-embedding-v2")
        dim_part = str(embedding_dimensions) if embedding_dimensions else ""
        base_key = f"{model}|d={dim_part}|fmt={vector_storage_format}"
        object.__setattr__(self, "_base_cache_key", base_key)
        object.__setattr__(
            self,
            "_document_cache_key",
            f"{base_key}|text_type={document_text_type}",
        )
        object.__setattr__(
            self,
            "_query_cache_key",
            f"{base_key}|text_type={query_text_type}",
        )
        object.__setattr__(
            self,
            "_cache",
            EmbeddingCache(cache_path, storage_format=vector_storage_format),
        )
        object.__setattr__(self, "_embedding_dimensions", embedding_dimensions)
        object.__setattr__(self, "_document_text_type", document_text_type)
        object.__setattr__(self, "_query_text_type", query_text_type)
        object.__setattr__(self, "_embed_max_chars", embed_max_chars)
        object.__setattr__(self, "_rate_limiter", rate_limiter)
        object.__setattr__(self, "_embed_retry_max", embed_retry_max)
        object.__setattr__(self, "_embed_backoff_base_ms", embed_backoff_base_ms)
        object.__setattr__(self, "_embed_backoff_max_ms", embed_backoff_max_ms)
        object.__setattr__(self, "cache_hits", 0)
        object.__setattr__(self, "api_calls", 0)
        object.__setattr__(self, "remote_batch_count", 0)

    def _sanitize_texts(self, texts: list[str]) -> list[str]:
        safe_texts = []
        for t in texts:
            if not t or not t.strip():
                safe_texts.append(" ")
            elif len(t) > self._embed_max_chars:
                safe_texts.append(t[: self._embed_max_chars])
            else:
                safe_texts.append(t)
        return safe_texts

    def _remote_api_batch_size(self) -> int:
        return DASHSCOPE_EMBED_BATCH_SIZES.get(self.model, 25)

    def _call_remote_embed_single_batch(self, texts: list[str], text_type: str) -> list[list[float]]:
        """对不超过 SDK 单批上限的文本发起一次（或数次内部重试）远端 embedding。"""
        client = self.client

        def _on_retry(attempt: int, retry_max: int, exc: Exception, sleep_sec: float) -> None:
            logger.warning(
                "Embedding API 失败，%ss 后重试 (%s/%s): %s",
                sleep_sec,
                attempt,
                retry_max,
                exc,
            )

        estimated_tokens = estimate_tokens_for_texts(texts)

        def _invoke() -> list[list[float]]:
            return call_with_retry(
                client,
                model=self.model,
                texts=texts,
                text_type=text_type,
                dimension=self._embedding_dimensions,
                retry_max=self._embed_retry_max,
                backoff_base_ms=self._embed_backoff_base_ms,
                backoff_max_ms=self._embed_backoff_max_ms,
                on_retry=_on_retry,
            )

        if self._rate_limiter is not None:
            with self._rate_limiter.request_slot(estimated_tokens):
                return _invoke()
        return _invoke()

    def _call_remote_embed(self, texts: list[str], text_type: str) -> list[list[float]]:
        """按 DashScope SDK 实际批大小拆分，每批单独申请限流槽。"""
        if not texts:
            return []
        batch_size = self._remote_api_batch_size()
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            sub = texts[i : i + batch_size]
            with self._stats_lock:
                self.remote_batch_count += 1
            vectors.extend(self._call_remote_embed_single_batch(sub, text_type))
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        safe_texts = self._sanitize_texts(texts)
        cached = self._cache.get_many(self._document_cache_key, safe_texts)

        uncached_indices = [i for i, t in enumerate(safe_texts) if cached[t] is None]

        with self._stats_lock:
            self.cache_hits += len(safe_texts) - len(uncached_indices)
            self.api_calls += len(uncached_indices)

        if uncached_indices:
            uncached_texts = [safe_texts[i] for i in uncached_indices]
            new_vectors = self._call_remote_embed(uncached_texts, self._document_text_type)
            to_cache = []
            for idx, vec in zip(uncached_indices, new_vectors):
                cached[safe_texts[idx]] = vec
                to_cache.append((safe_texts[idx], vec))
            self._cache.put_many(self._document_cache_key, to_cache)

        return [cached[t] for t in safe_texts]

    def embed_query(self, text: str) -> list[float]:
        safe = (text[: self._embed_max_chars] if text and len(text) > self._embed_max_chars else text) or " "
        result = self._cache.get_many(self._query_cache_key, [safe])
        if result[safe] is not None:
            with self._stats_lock:
                self.cache_hits += 1
            return result[safe]
        with self._stats_lock:
            self.api_calls += 1
        vec = self._call_remote_embed([safe], self._query_text_type)[0]
        self._cache.put_many(self._query_cache_key, [(safe, vec)])
        return vec

    def stats_snapshot(self) -> EmbeddingStatsSnapshot:
        with self._stats_lock:
            return EmbeddingStatsSnapshot(
                cache_hit_text_count=self.cache_hits,
                uncached_text_count=self.api_calls,
                remote_batch_count=self.remote_batch_count,
            )

    def stats_str(self) -> str:
        snapshot = self.stats_snapshot()
        total = snapshot.cache_hit_text_count + snapshot.uncached_text_count
        if total == 0:
            return "无嵌入调用"
        return (
            f"远端文本: {snapshot.uncached_text_count} / {total} "
            f"({snapshot.cache_hit_text_count} 缓存命中, {snapshot.remote_batch_count} 批次)"
        )

    def cleanup_cache(self, max_age_days: int = 30) -> int:
        return self._cache.cleanup_old_entries(max_age_days)
