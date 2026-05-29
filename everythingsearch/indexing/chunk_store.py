"""ChunkStore：以 sparse_chunks 表为权威正文来源。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChunkRecord:
    """稀疏库中的 chunk 正文记录。"""

    chunk_id: str
    content: str
    title_path: tuple[str, ...]


def fetch_chunks_by_ids(sparse_index_path: str, chunk_ids: list[str]) -> dict[str, ChunkRecord]:
    """按 chunk_id 批量读取正文与 title_path。"""
    if not chunk_ids:
        return {}
    db_file = Path(sparse_index_path)
    if not db_file.is_file():
        return {}

    unique_ids = list(dict.fromkeys(chunk_ids))
    result: dict[str, ChunkRecord] = {}
    placeholders = ",".join("?" * len(unique_ids))
    sql = (
        f"SELECT chunk_id, content, title_path FROM sparse_chunks "
        f"WHERE chunk_id IN ({placeholders})"
    )
    with sqlite3.connect(str(db_file), timeout=30.0) as conn:
        rows = conn.execute(sql, unique_ids).fetchall()
    for chunk_id, content, title_path_json in rows:
        try:
            parsed = json.loads(title_path_json or "[]")
            title_path = tuple(parsed) if isinstance(parsed, list) else ()
        except (TypeError, ValueError):
            title_path = ()
        result[str(chunk_id)] = ChunkRecord(
            chunk_id=str(chunk_id),
            content=str(content or ""),
            title_path=title_path,
        )
    return result
