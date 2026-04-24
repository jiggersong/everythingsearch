"""检索模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

@dataclass(frozen=True)
class QueryPlan:
    """检索计划。"""

    raw_query: str
    normalized_query: str
    sparse_query: str
    dense_query: str
    query_type: Literal["exact", "semantic", "hybrid", "filename", "code"]
    exactness_level: Literal["low", "medium", "high"]
    source_filter: str | None
    date_field: Literal["mtime", "ctime"]
    date_from: float | None
    date_to: float | None
    sparse_top_k: int
    dense_top_k: int
    fusion_top_k: int
    rerank_top_k: int
    path_filter: str | None = None
    filename_only: bool = False


@dataclass(frozen=True)
class SearchCandidate:
    """召回阶段返回的候选 chunk。"""

    chunk_id: str
    file_id: str
    filepath: str
    filename: str
    chunk_type: str
    content: str
    title_path: tuple[str, ...]
    source_type: str
    filetype: str
    sparse_rank: int | None = None
    dense_rank: int | None = None
    sparse_score: float | None = None
    dense_score: float | None = None
    fusion_score: float = 0.0
    rerank_rank: int | None = None
    rerank_score: float | None = None
    metadata: Mapping[str, str | int | float | bool] = field(default_factory=dict)

@dataclass(frozen=True)
class AggregatedResult:
    """聚合后的文件级结果，用于给最终客户端展示。"""

    file_id: str
    filename: str
    filepath: str
    source_type: str
    filetype: str
    mtime: float
    score: float
    best_chunk_type: str
    highlights: list[str]
    metadata: Mapping[str, str | int | float | bool]
