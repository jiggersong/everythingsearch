"""全量重建断点状态表（流程级续跑）。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from everythingsearch.infra.settings import Settings

PHASE_CONVERTING = "converting"
PHASE_SPARSE = "sparse"
PHASE_DENSE = "dense"
PHASE_COMPLETED = "completed"


@dataclass(frozen=True)
class RebuildCheckpoint:
    """重建断点快照。"""

    run_id: str
    config_fingerprint: str
    phase: str
    sparse_batch_end: int
    dense_batch_end: int
    total_chunks: int
    updated_at: float


def compute_rebuild_config_fingerprint(settings: Settings) -> str:
    """根据关键索引参数生成指纹，避免错误续跑。"""
    payload = {
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "embedding_document_text_type": settings.embedding_document_text_type,
        "embedding_query_text_type": settings.embedding_query_text_type,
        "embed_vector_storage_format": settings.embed_vector_storage_format,
        "persist_directory": settings.persist_directory,
        "sparse_index_path": settings.sparse_index_path,
        "embedding_cache_path": settings.embedding_cache_path,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class RebuildCheckpointStore:
    """SQLite 持久化的重建断点存储。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rebuild_checkpoint (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    run_id TEXT NOT NULL,
                    config_fingerprint TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    sparse_batch_end INTEGER NOT NULL,
                    dense_batch_end INTEGER NOT NULL,
                    total_chunks INTEGER NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def load(self) -> RebuildCheckpoint | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT run_id, config_fingerprint, phase,
                       sparse_batch_end, dense_batch_end, total_chunks, updated_at
                FROM rebuild_checkpoint WHERE id = 1
                """
            ).fetchone()
        if not row:
            return None
        return RebuildCheckpoint(
            run_id=row[0],
            config_fingerprint=row[1],
            phase=row[2],
            sparse_batch_end=int(row[3]),
            dense_batch_end=int(row[4]),
            total_chunks=int(row[5]),
            updated_at=float(row[6]),
        )

    def save(
        self,
        *,
        run_id: str,
        config_fingerprint: str,
        phase: str,
        sparse_batch_end: int,
        dense_batch_end: int,
        total_chunks: int,
    ) -> None:
        now = time.time()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM rebuild_checkpoint WHERE id = 1")
            conn.execute(
                """
                INSERT INTO rebuild_checkpoint (
                    id, run_id, config_fingerprint, phase,
                    sparse_batch_end, dense_batch_end, total_chunks, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    config_fingerprint,
                    phase,
                    sparse_batch_end,
                    dense_batch_end,
                    total_chunks,
                    now,
                ),
            )
            conn.commit()

    def clear(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM rebuild_checkpoint")
            conn.commit()

    def is_resumable(self, settings: Settings) -> RebuildCheckpoint | None:
        """若指纹匹配且未完成，则返回可续跑断点。"""
        checkpoint = self.load()
        if checkpoint is None:
            return None
        if checkpoint.phase == PHASE_COMPLETED:
            return None
        fingerprint = compute_rebuild_config_fingerprint(settings)
        if checkpoint.config_fingerprint != fingerprint:
            return None
        return checkpoint
