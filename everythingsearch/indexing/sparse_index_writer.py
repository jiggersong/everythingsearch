"""稀疏索引写入模块。"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Protocol

import jieba

from everythingsearch.infra.settings import Settings
from everythingsearch.indexing.chunk_models import IndexedChunk

logger = logging.getLogger(__name__)


class SparseIndexWriter(Protocol):
    """稀疏索引写入器协议。"""

    def upsert_chunks(self, chunks: list[IndexedChunk]) -> None:
        """写入或更新稀疏索引块。"""

    def delete_file(self, file_id: str) -> None:
        """删除指定文件的所有稀疏索引块。"""

    def optimize(self) -> None:
        """优化稀疏索引库（例如 FTS5 的 optimize 指令）。"""


class SQLiteSparseIndexWriter:
    """基于 SQLite FTS5 的稀疏索引写入器。"""

    def __init__(self, settings: Settings) -> None:
        """初始化。

        Args:
            settings: 包含 sparse_index_path 等配置的 Settings 实例。
        """
        self._db_path = settings.sparse_index_path
        self._ensure_db_and_tables()

    def _ensure_db_and_tables(self) -> None:
        """确保数据库文件及相关表存在。"""
        db_file = Path(self._db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        import contextlib
        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                # 开启 WAL 模式提高并发性能
                conn.execute("PRAGMA journal_mode=WAL")
                # 开启外键支持
                conn.execute("PRAGMA foreign_keys=ON")

                # 原文与元数据表
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

                # 为了能通过 file_id 快速删除记录，建立索引
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_sparse_chunks_file_id ON sparse_chunks(file_id)"
                )

                # FTS5 虚拟表，使用 unicode61 tokenizer
                # 实际写入的数据将使用 jieba 进行预分词，以空格连接
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

                # FTS5 的外部内容同步触发器 (可选，但为了解耦我们在这里在代码里手动双写，不用 trigger)
                # 因为我们在向 FTS 写入时需要进行 jieba 分词，不能直接使用 trigger 复制原始列。
                conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接。"""
        # 使用超时并允许在多线程中共享连接（仅做读写操作时通过上下文管理控制事务）
        return sqlite3.connect(self._db_path, timeout=30.0, check_same_thread=False)

    def _tokenize_text(self, text: str) -> str:
        """使用 jieba 对文本进行分词处理，以便存入 FTS5。"""
        if not text:
            return ""
        # 使用 cut_for_search 以提高长难句中短词的召回率
        tokens = jieba.cut_for_search(text)
        # 用空格连接，以便 unicode61 分词器能将它们切分为独立的 token
        return " ".join(tokens)

    def upsert_chunks(self, chunks: list[IndexedChunk]) -> None:
        if not chunks:
            return

        import contextlib
        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                
                # 首先，处理所有的 chunk_id，可能存在替换
                chunk_ids = [chunk.chunk_id for chunk in chunks]
                
                # 由于可能存在相同 chunk_id 的更新，我们使用 REPLACE INTO
                
                insert_chunks_sql = """
                    REPLACE INTO sparse_chunks (
                        chunk_id, file_id, filepath, filename, source_type, filetype,
                        chunk_type, title_path, content, mtime, ctime, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                
                # 更新 FTS 表比较麻烦，如果存在旧记录需要先删除。
                # 为了简单起见，我们先删掉这些 chunk_id 在 FTS 表中的旧记录。
                # FIXME: delete in FTS5 without rowid is O(N) and slow. Disabled for pipeline indexing.
                # delete_fts_sql = "DELETE FROM sparse_chunks_fts WHERE chunk_id = ?"
                # cursor.executemany(delete_fts_sql, [(cid,) for cid in chunk_ids])

                insert_fts_sql = """
                    INSERT INTO sparse_chunks_fts (
                        filename, path_text, heading_text, content_text, chunk_id, file_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """

                chunk_records = []
                fts_records = []

                for chunk in chunks:
                    try:
                        title_path_json = json.dumps(chunk.title_path, ensure_ascii=False)
                        metadata_json = json.dumps(chunk.metadata, ensure_ascii=False)
                    except (TypeError, ValueError) as exc:
                        logger.warning("无法序列化 chunk %s 的数据: %s", chunk.chunk_id, exc)
                        title_path_json = "[]"
                        metadata_json = "{}"

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
                        metadata_json
                    ))

                    # 为 FTS 表准备预分词文本
                    # 结合设计：filename 权重最高，heading 次之。
                    # path_text 可用于路径搜索。
                    fts_filename = self._tokenize_text(chunk.filename)
                    fts_path_text = self._tokenize_text(chunk.filepath)
                    fts_heading_text = self._tokenize_text(" ".join(chunk.title_path))
                    fts_content_text = self._tokenize_text(chunk.sparse_text)

                    fts_records.append((
                        fts_filename,
                        fts_path_text,
                        fts_heading_text,
                        fts_content_text,
                        chunk.chunk_id,
                        chunk.file_id
                    ))

                cursor.executemany(insert_chunks_sql, chunk_records)
                cursor.executemany(insert_fts_sql, fts_records)
                
            logger.debug("成功 upsert %d 个稀疏索引块", len(chunks))

    def delete_file(self, file_id: str) -> None:
        if not file_id:
            return

        import contextlib
        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                # 从 FTS 表中删除
                cursor.execute("DELETE FROM sparse_chunks_fts WHERE file_id = ?", (file_id,))
                # 从原数据表中删除
                cursor.execute("DELETE FROM sparse_chunks WHERE file_id = ?", (file_id,))
            logger.debug("已删除 file_id='%s' 的所有稀疏索引", file_id)

    def optimize(self) -> None:
        try:
            import contextlib
            with contextlib.closing(self._get_connection()) as conn:
                with conn:
                    # FTS5 的 optimize 指令会将内部的 b-tree 结构合并为一个大的 b-tree，提升查询速度。
                    conn.execute("INSERT INTO sparse_chunks_fts(sparse_chunks_fts) VALUES('optimize')")
                logger.info("稀疏索引 FTS5 optimize 执行完成")
        except sqlite3.Error as exc:
            logger.error("稀疏索引优化失败: %s", exc)
