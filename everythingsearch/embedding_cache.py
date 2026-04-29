import hashlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any
from queue import Queue, Empty

from pydantic import ConfigDict, PrivateAttr
from langchain_community.embeddings import DashScopeEmbeddings

logger = logging.getLogger(__name__)


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
        # 启用 WAL 模式提高并发性能
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
            # 如果池子空了，创建临时连接（超过 max_connections 限制）
            logger.warning("连接池耗尽，创建临时连接")
            return self._create_connection()
    
    def return_connection(self, conn: sqlite3.Connection):
        """归还连接到池"""
        try:
            # 简单健康检查
            conn.execute("SELECT 1")
            self._pool.put(conn, block=False)
        except (sqlite3.Error, Exception):
            # 连接损坏，关闭它
            try:
                conn.close()
            except:
                pass
    
    def close_all(self):
        """关闭所有连接"""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except:
                pass


class EmbeddingCache:
    """Thread-safe SQLite cache for embedding vectors with connection pool."""

    def __init__(self, db_path: str, max_connections: int = 5):
        self.db_path = db_path
        self._pool = ConnectionPool(db_path, max_connections)
        self._init_db()

    def _init_db(self):
        """初始化数据库表；旧版仅两列的表会迁移增加 created_at。"""
        conn = self._pool.get_connection()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS embeddings "
                "(text_hash TEXT PRIMARY KEY, vector TEXT, created_at REAL)"
            )
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'"
            ).fetchone()
            if row:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(embeddings)").fetchall()}
                if "created_at" not in cols:
                    conn.execute("ALTER TABLE embeddings ADD COLUMN created_at REAL")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_created_at ON embeddings(created_at)"
            )
            conn.commit()
        finally:
            self._pool.return_connection(conn)

    @staticmethod
    def _hash(model: str, text: str) -> str:
        return hashlib.sha256(f"{model}::{text}".encode("utf-8")).hexdigest()

    def get_many(self, model: str, texts: list[str]) -> dict[str, list[float] | None]:
        hashes = {self._hash(model, t): t for t in texts}
        result: dict[str, list[float] | None] = {t: None for t in texts}

        conn = self._pool.get_connection()
        try:
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
        finally:
            self._pool.return_connection(conn)
        return result

    def put_many(self, model: str, items: list[tuple[str, list[float]]]):
        """批量写入缓存，包含创建时间"""
        now = time.time()
        conn = self._pool.get_connection()
        try:
            rows = [(self._hash(model, text), json.dumps(vec), now) for text, vec in items]
            conn.executemany(
                "INSERT OR REPLACE INTO embeddings (text_hash, vector, created_at) VALUES (?, ?, ?)",
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
                # 执行 VACUUM 回收空间
                conn.execute("VACUUM")
            return deleted
        finally:
            self._pool.return_connection(conn)


class CachedEmbeddings(DashScopeEmbeddings):
    """DashScopeEmbeddings with a transparent SQLite cache layer."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _cache: Any = None
    cache_hits: int = 0
    api_calls: int = 0
    remote_batch_count: int = 0
    _stats_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    def __init__(self, cache_path: str, **kwargs):
        if not cache_path or not str(cache_path).strip():
            raise ValueError("CachedEmbeddings 需要 cache_path（请传入 config.EMBEDDING_CACHE_PATH）")
        super().__init__(**kwargs)
        object.__setattr__(self, "_cache", EmbeddingCache(cache_path))
        object.__setattr__(self, "cache_hits", 0)
        object.__setattr__(self, "api_calls", 0)
        object.__setattr__(self, "remote_batch_count", 0)

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

        with self._stats_lock:
            self.cache_hits += len(safe_texts) - len(uncached_indices)
            self.api_calls += len(uncached_indices)

        if uncached_indices:
            uncached_texts = [safe_texts[i] for i in uncached_indices]
            with self._stats_lock:
                self.remote_batch_count += 1
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
            with self._stats_lock:
                self.cache_hits += 1
            return result[safe]
        with self._stats_lock:
            self.api_calls += 1
            self.remote_batch_count += 1
        vec = super().embed_query(safe)
        self._cache.put_many(self.model, [(safe, vec)])
        return vec

    def stats_snapshot(self) -> EmbeddingStatsSnapshot:
        """返回当前 embedding 缓存与远端调用统计快照。"""
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
        """清理旧缓存条目"""
        return self._cache.cleanup_old_entries(max_age_days)
