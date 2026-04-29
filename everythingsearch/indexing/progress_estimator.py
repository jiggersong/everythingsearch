"""索引任务规模、耗时与 Token 成本估算。"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
import sqlite3

from everythingsearch.indexing.chunk_models import IndexedChunk

DEFAULT_CHARS_PER_TOKEN = 1.5
DEFAULT_EMBEDDING_MAX_CHARS = 600
DEFAULT_CHUNKS_PER_FILE = 4.0
DEFAULT_SECONDS_PER_FILE = 0.35


@dataclass(frozen=True)
class IndexScaleSnapshot:
    """索引任务启动前的文件规模快照。"""

    disk_file_count: int
    mweb_note_count: int
    new_file_count: int = 0
    modified_file_count: int = 0
    deleted_file_count: int = 0
    pending_file_count: int = 0
    existing_state_file_count: int = 0


@dataclass(frozen=True)
class IndexCostEstimate:
    """索引任务成本与耗时预估。"""

    estimated_chunk_count: int
    estimated_input_token_count: int
    estimated_remote_embedding_text_count: int
    estimated_total_seconds: float
    confidence_level: str
    notes: tuple[str, ...] = ()


def normalize_embedding_text_for_estimate(
    text: str | None,
    max_chars: int = DEFAULT_EMBEDDING_MAX_CHARS,
) -> str:
    """按实际 embedding 截断口径标准化估算文本。

    Args:
        text: 原始 embedding 输入文本。
        max_chars: 与 `CachedEmbeddings._EMBED_MAX` 对齐的最大字符数。

    Returns:
        str: 空文本归一化为空格，非空文本最多保留 `max_chars` 个字符。
    """
    if not text or not text.strip():
        return " "
    return text[:max_chars]


def estimate_tokens_from_text(
    text: str | None,
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
    max_chars: int = DEFAULT_EMBEDDING_MAX_CHARS,
) -> int:
    """根据最终送入 embedding 的截断文本长度估算 Token 数。

    Args:
        text: 原始 embedding 输入文本。
        chars_per_token: 平均每 token 对应的字符数。
        max_chars: 估算前的最大字符截断长度。

    Returns:
        int: 至少为 1 的估算 Token 数。

    Raises:
        ValueError: `chars_per_token` 或 `max_chars` 非正数。
    """
    if chars_per_token <= 0:
        raise ValueError("chars_per_token 必须大于 0")
    if max_chars <= 0:
        raise ValueError("max_chars 必须大于 0")
    safe_text = normalize_embedding_text_for_estimate(text, max_chars=max_chars)
    return max(1, math.ceil(len(safe_text) / chars_per_token))


def estimate_tokens_from_texts(texts: list[str]) -> int:
    """批量估算 embedding 输入 Token 数。

    Args:
        texts: 原始 embedding 输入文本列表。

    Returns:
        int: 估算 Token 总数。
    """
    return sum(estimate_tokens_from_text(text) for text in texts)


def estimate_incremental_cost(
    pending_file_count: int,
    historical_chunks_per_file: float | None = None,
    historical_seconds_per_file: float | None = None,
) -> IndexCostEstimate:
    """在尚未解析文件内容前，估算增量任务成本。

    Args:
        pending_file_count: 待新增或修改的文件数。
        historical_chunks_per_file: 历史平均每文件 chunk 数。
        historical_seconds_per_file: 历史平均每文件处理秒数。

    Returns:
        IndexCostEstimate: 启动前粗略估算。
    """
    return _estimate_cost_from_file_count(
        pending_file_count,
        historical_chunks_per_file=historical_chunks_per_file,
        historical_seconds_per_file=historical_seconds_per_file,
        confidence_level="low",
        note="增量预估基于待处理文件数量，实际值会在解析文件后修正。",
    )


def estimate_full_cost_from_file_count(
    file_count: int,
    historical_chunks_per_file: float | None = None,
    historical_seconds_per_file: float | None = None,
) -> IndexCostEstimate:
    """在全量任务扫描前，按文件数量估算成本。

    Args:
        file_count: 预计参与全量构建的文件数。
        historical_chunks_per_file: 历史平均每文件 chunk 数。
        historical_seconds_per_file: 历史平均每文件处理秒数。

    Returns:
        IndexCostEstimate: 启动前粗略估算。
    """
    return _estimate_cost_from_file_count(
        file_count,
        historical_chunks_per_file=historical_chunks_per_file,
        historical_seconds_per_file=historical_seconds_per_file,
        confidence_level="low",
        note="全量初始预估基于轻量文件盘点，扫描切块完成后会修正。",
    )


def estimate_cost_from_chunks(chunks: list[IndexedChunk]) -> IndexCostEstimate:
    """在 chunk 已生成后，按实际 embedding_text 估算成本。

    Args:
        chunks: 已构造的索引 chunk 列表。

    Returns:
        IndexCostEstimate: 基于实际 chunk 文本的较高可信估算。
    """
    token_count = estimate_tokens_from_texts([chunk.embedding_text for chunk in chunks])
    return IndexCostEstimate(
        estimated_chunk_count=len(chunks),
        estimated_input_token_count=token_count,
        estimated_remote_embedding_text_count=len(chunks),
        estimated_total_seconds=len(chunks) * DEFAULT_SECONDS_PER_FILE / DEFAULT_CHUNKS_PER_FILE,
        confidence_level="medium",
        notes=("Token 估算已按 embedding 600 字符截断口径计算。",),
    )


def load_historical_chunks_per_file(
    sparse_index_path: str,
    fallback_file_count: int,
) -> float | None:
    """从 sparse index 中读取历史平均每文件 chunk 数。

    Args:
        sparse_index_path: SQLite sparse index 路径。
        fallback_file_count: sparse 库不可用时用于判断是否返回默认值的文件数。

    Returns:
        float | None: 可用历史均值；没有历史数据时返回 None。
    """
    if fallback_file_count <= 0:
        return None
    if not os.path.isfile(sparse_index_path):
        return None
    try:
        conn = sqlite3.connect(sparse_index_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*), COUNT(DISTINCT file_id) FROM sparse_chunks"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    chunk_count, file_count = int(row[0] or 0), int(row[1] or 0)
    if chunk_count <= 0 or file_count <= 0:
        return None
    return chunk_count / file_count


def _estimate_cost_from_file_count(
    file_count: int,
    *,
    historical_chunks_per_file: float | None,
    historical_seconds_per_file: float | None,
    confidence_level: str,
    note: str,
) -> IndexCostEstimate:
    safe_file_count = max(0, file_count)
    if safe_file_count == 0:
        return IndexCostEstimate(
            estimated_chunk_count=0,
            estimated_input_token_count=0,
            estimated_remote_embedding_text_count=0,
            estimated_total_seconds=0.0,
            confidence_level="high",
            notes=("无待处理文件。",),
        )
    chunks_per_file = historical_chunks_per_file or DEFAULT_CHUNKS_PER_FILE
    seconds_per_file = historical_seconds_per_file or DEFAULT_SECONDS_PER_FILE
    estimated_chunk_count = max(1, math.ceil(safe_file_count * chunks_per_file))
    # 启动前没有正文，只能按 600 字符上限保守估算每个 chunk。
    estimated_input_token_count = estimated_chunk_count * estimate_tokens_from_text(
        "x" * DEFAULT_EMBEDDING_MAX_CHARS
    )
    return IndexCostEstimate(
        estimated_chunk_count=estimated_chunk_count,
        estimated_input_token_count=estimated_input_token_count,
        estimated_remote_embedding_text_count=estimated_chunk_count,
        estimated_total_seconds=safe_file_count * seconds_per_file,
        confidence_level=confidence_level,
        notes=(note,),
    )
