"""全量重建中间结果暂存（供断点续跑加载 chunk 列表）。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from everythingsearch.indexing.chunk_models import IndexedChunk

STAGING_BATCH_SIZE = 5000


def _chunk_to_row(sequence_no: int, chunk: IndexedChunk) -> tuple:
    return (
        sequence_no,
        chunk.chunk_id,
        chunk.file_id,
        chunk.filepath,
        chunk.filename,
        chunk.source_type,
        chunk.filetype,
        chunk.chunk_type,
        json.dumps(chunk.title_path, ensure_ascii=False),
        chunk.content,
        chunk.embedding_text,
        chunk.sparse_text,
        chunk.chunk_index,
        chunk.mtime,
        chunk.ctime,
        json.dumps(dict(chunk.metadata), ensure_ascii=False),
    )


def _row_to_chunk(row: tuple) -> IndexedChunk:
    (
        _sequence_no,
        chunk_id,
        file_id,
        filepath,
        filename,
        source_type,
        filetype,
        chunk_type,
        title_path_json,
        content,
        embedding_text,
        sparse_text,
        chunk_index,
        mtime,
        ctime,
        metadata_json,
    ) = row
    title_path = tuple(json.loads(title_path_json or "[]"))
    metadata = json.loads(metadata_json or "{}")
    return IndexedChunk(
        chunk_id=chunk_id,
        file_id=file_id,
        filepath=filepath,
        filename=filename,
        source_type=source_type,
        filetype=filetype,
        chunk_type=chunk_type,
        title_path=title_path,
        content=content,
        embedding_text=embedding_text,
        sparse_text=sparse_text,
        chunk_index=int(chunk_index),
        mtime=float(mtime),
        ctime=float(ctime),
        metadata=metadata,
    )


class RebuildStagingStore:
    """将转换后的 IndexedChunk 列表持久化，供续跑加载。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='rebuild_chunks'"
            ).fetchone()
            if row:
                cols = {r[1] for r in conn.execute("PRAGMA table_info(rebuild_chunks)").fetchall()}
                if "sequence_no" not in cols:
                    conn.execute("DROP TABLE rebuild_chunks")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rebuild_chunks (
                    sequence_no INTEGER PRIMARY KEY,
                    chunk_id TEXT NOT NULL UNIQUE,
                    file_id TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    filetype TEXT NOT NULL,
                    chunk_type TEXT NOT NULL,
                    title_path TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_text TEXT NOT NULL,
                    sparse_text TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    ctime REAL NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def clear(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM rebuild_chunks")
            conn.commit()

    def save_chunks(self, chunks: list[IndexedChunk]) -> None:
        self.clear()
        if not chunks:
            return
        insert_sql = """
            INSERT INTO rebuild_chunks (
                sequence_no, chunk_id, file_id, filepath, filename, source_type, filetype,
                chunk_type, title_path, content, embedding_text, sparse_text,
                chunk_index, mtime, ctime, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with sqlite3.connect(self._db_path) as conn:
            for start in range(0, len(chunks), STAGING_BATCH_SIZE):
                batch = chunks[start : start + STAGING_BATCH_SIZE]
                rows = [
                    _chunk_to_row(start + offset, chunk)
                    for offset, chunk in enumerate(batch)
                ]
                conn.executemany(insert_sql, rows)
                conn.commit()

    def load_chunks(self) -> list[IndexedChunk]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT sequence_no, chunk_id, file_id, filepath, filename, source_type, filetype,
                       chunk_type, title_path, content, embedding_text, sparse_text,
                       chunk_index, mtime, ctime, metadata_json
                FROM rebuild_chunks ORDER BY sequence_no
                """
            ).fetchall()
        return [_row_to_chunk(row) for row in rows]

    def count(self) -> int:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM rebuild_chunks").fetchone()
        return int(row[0]) if row else 0
