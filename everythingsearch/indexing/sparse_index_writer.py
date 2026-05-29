"""稀疏索引写入模块。"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import jieba

from everythingsearch.infra.settings import Settings
from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.indexing.chunk_conversion import compact_title_path

logger = logging.getLogger(__name__)


class SparseIndexWriter(Protocol):
    """稀疏索引写入器协议。"""

    def upsert_chunks(self, chunks: list[IndexedChunk]) -> None:
        """写入或更新稀疏索引块。"""

    def delete_file(self, file_id: str) -> None:
        """删除指定文件的所有稀疏索引块。"""

    def optimize(self) -> None:
        """优化稀疏索引库（例如 FTS5 的 optimize 指令）。"""


@dataclass(frozen=True)
class PreparedSparseRecords:
    """已分词、待写入 SQLite 的记录批次。"""

    chunk_records: tuple[tuple, ...]
    fts_records: tuple[tuple, ...]
    chunk_ids: tuple[str, ...]

    @classmethod
    def merge(cls, parts: list[PreparedSparseRecords]) -> PreparedSparseRecords:
        chunk_records: list[tuple] = []
        fts_records: list[tuple] = []
        chunk_ids: list[str] = []
        for part in parts:
            chunk_records.extend(part.chunk_records)
            fts_records.extend(part.fts_records)
            chunk_ids.extend(part.chunk_ids)
        return cls(
            chunk_records=tuple(chunk_records),
            fts_records=tuple(fts_records),
            chunk_ids=tuple(chunk_ids),
        )


class SparseBulkSession:
    """Sparse 批量写入会话：长连接 + 可选 fast PRAGMA。"""

    def __init__(
        self,
        writer: SQLiteSparseIndexWriter,
        *,
        skip_fts_delete: bool = False,
        use_fast_pragma: bool = True,
    ) -> None:
        self._writer = writer
        self._skip_fts_delete = skip_fts_delete
        self._use_fast_pragma = use_fast_pragma
        self._conn: sqlite3.Connection | None = None
        self._prev_sync: str | None = None

    def __enter__(self) -> SparseBulkSession:
        self._conn = self._writer._get_connection()
        if self._use_fast_pragma and self._writer._settings.sparse_bulk_pragma_fast:
            row = self._conn.execute("PRAGMA synchronous").fetchone()
            self._prev_sync = row[0] if row else "FULL"
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=-64000")
            self._conn.execute("PRAGMA temp_store=MEMORY")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._conn is None:
            return
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
            if self._prev_sync is not None:
                self._conn.execute(f"PRAGMA synchronous={self._prev_sync}")
        finally:
            self._conn.close()
            self._conn = None

    def write_prepared(self, prepared: PreparedSparseRecords) -> None:
        if self._conn is None:
            raise RuntimeError("SparseBulkSession 未进入上下文")
        self._writer.write_prepared(
            self._conn,
            prepared,
            skip_fts_delete=self._skip_fts_delete,
        )
        self._conn.commit()


class SQLiteSparseIndexWriter:
    """基于 SQLite FTS5 的稀疏索引写入器。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db_path = settings.sparse_index_path
        self._ensure_db_and_tables()

    def _ensure_db_and_tables(self) -> None:
        """确保数据库文件及相关表存在。"""
        db_file = Path(self._db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        import contextlib
        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sparse_chunks (
                        chunk_id TEXT PRIMARY KEY,
                        file_id TEXT NOT NULL,
                        filepath TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        filetype TEXT NOT NULL,
                        chunk_type TEXT NOT NULL,
                        title_path TEXT NOT NULL,
                        content TEXT NOT NULL,
                        mtime REAL NOT NULL,
                        ctime REAL NOT NULL,
                        metadata_json TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sparse_chunks_file_id ON sparse_chunks(file_id)"
                )
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS sparse_chunks_fts USING fts5(
                        filename,
                        path_text,
                        heading_text,
                        content_text,
                        chunk_id UNINDEXED,
                        file_id UNINDEXED,
                        tokenize = 'unicode61'
                    )
                    """
                )
                conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=30.0, check_same_thread=False)

    _CJK_RE = re.compile(r'[一-鿿㐀-䶿\U00020000-\U0002a6df]+')

    @classmethod
    def _extract_cjk_bigrams(cls, text: str) -> list[str]:
        bigrams: list[str] = []
        for match in cls._CJK_RE.finditer(text):
            segment = match.group()
            if len(segment) < 2:
                continue
            bigrams.extend(segment[i:i + 2] for i in range(len(segment) - 1))
        return bigrams

    def _tokenize_text(self, text: str) -> str:
        if not text:
            return ""
        tokens = list(jieba.cut_for_search(text))
        tokens.extend(self._extract_cjk_bigrams(text))
        return " ".join(tokens)

    def prepare_batch(self, chunks: list[IndexedChunk]) -> PreparedSparseRecords:
        """CPU 阶段：jieba 分词与行组装（可在线程池调用）。"""
        if not chunks:
            return PreparedSparseRecords((), (), ())

        chunk_records: list[tuple] = []
        fts_records: list[tuple] = []
        chunk_ids: list[str] = []

        for chunk in chunks:
            compacted_title_path = compact_title_path(chunk.title_path)
            try:
                title_path_json = json.dumps(compacted_title_path, ensure_ascii=False)
                metadata_json = json.dumps(chunk.metadata, ensure_ascii=False)
            except (TypeError, ValueError) as exc:
                logger.warning("无法序列化 chunk %s 的数据: %s", chunk.chunk_id, exc)
                title_path_json = "[]"
                metadata_json = "{}"

            chunk_ids.append(chunk.chunk_id)
            chunk_records.append((
                chunk.chunk_id,
                chunk.file_id,
                chunk.filepath,
                chunk.filename,
                chunk.source_type,
                chunk.filetype,
                chunk.chunk_type,
                title_path_json,
                chunk.content,
                chunk.mtime,
                chunk.ctime,
                metadata_json,
            ))
            fts_records.append((
                self._tokenize_text(chunk.filename),
                self._tokenize_text(chunk.filepath[-180:]),
                self._tokenize_text(" ".join(compacted_title_path)),
                self._tokenize_text(chunk.sparse_text),
                chunk.chunk_id,
                chunk.file_id,
            ))

        return PreparedSparseRecords(
            chunk_records=tuple(chunk_records),
            fts_records=tuple(fts_records),
            chunk_ids=tuple(chunk_ids),
        )

    def write_prepared(
        self,
        conn: sqlite3.Connection,
        prepared: PreparedSparseRecords,
        *,
        skip_fts_delete: bool = False,
    ) -> None:
        """在已有连接上写入 prepared 记录（单写者）。"""
        if not prepared.chunk_records:
            return

        cursor = conn.cursor()
        insert_chunks_sql = """
            REPLACE INTO sparse_chunks (
                chunk_id, file_id, filepath, filename, source_type, filetype,
                chunk_type, title_path, content, mtime, ctime, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        if not skip_fts_delete:
            delete_fts_sql = "DELETE FROM sparse_chunks_fts WHERE chunk_id = ?"
            cursor.executemany(delete_fts_sql, [(cid,) for cid in prepared.chunk_ids])

        insert_fts_sql = """
            INSERT INTO sparse_chunks_fts (
                filename, path_text, heading_text, content_text, chunk_id, file_id
            ) VALUES (?, ?, ?, ?, ?, ?)
        """
        cursor.executemany(insert_chunks_sql, prepared.chunk_records)
        cursor.executemany(insert_fts_sql, prepared.fts_records)

    def open_bulk_session(self, *, skip_fts_delete: bool = False) -> SparseBulkSession:
        return SparseBulkSession(
            self,
            skip_fts_delete=skip_fts_delete,
            use_fast_pragma=True,
        )

    def upsert_chunks(self, chunks: list[IndexedChunk]) -> None:
        if not chunks:
            return
        prepared = self.prepare_batch(chunks)
        import contextlib
        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                self.write_prepared(conn, prepared, skip_fts_delete=False)
        logger.debug("成功 upsert %d 个稀疏索引块", len(chunks))

    def delete_file(self, file_id: str) -> None:
        if not file_id:
            return
        import contextlib
        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM sparse_chunks_fts WHERE file_id = ?", (file_id,))
                cursor.execute("DELETE FROM sparse_chunks WHERE file_id = ?", (file_id,))
            logger.debug("已删除 file_id='%s' 的所有稀疏索引", file_id)

    def optimize(self) -> None:
        try:
            import contextlib
            with contextlib.closing(self._get_connection()) as conn:
                with conn:
                    conn.execute("INSERT INTO sparse_chunks_fts(sparse_chunks_fts) VALUES('optimize')")
                logger.info("稀疏索引 FTS5 optimize 执行完成")
        except sqlite3.Error as exc:
            logger.error("稀疏索引优化失败: %s", exc)


def resolve_sparse_tokenize_workers(settings: Settings) -> int:
    """解析并行 jieba worker 数。"""
    configured = settings.sparse_tokenize_workers
    if configured > 0:
        return configured
    cpu = os.cpu_count() or 4
    return min(8, max(4, cpu - 1))
