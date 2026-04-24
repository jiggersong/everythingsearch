"""索引数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping


@dataclass(frozen=True)
class IndexedChunk:
    """索引块，是 sparse 与 dense 两套索引的共同写入单位。"""

    chunk_id: str
    file_id: str
    filepath: str
    filename: str
    source_type: str
    filetype: str
    chunk_type: Literal["filename", "heading", "content", "table", "slide", "code"]
    title_path: tuple[str, ...]
    content: str
    embedding_text: str
    sparse_text: str
    chunk_index: int
    mtime: float
    ctime: float
    metadata: Mapping[str, str | int | float | bool]
