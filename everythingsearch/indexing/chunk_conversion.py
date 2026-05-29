"""IndexedChunk 转换与字段归一化工具。"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from langchain_core.documents import Document

from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.infra.settings import Settings, get_settings


def generate_file_id(filepath: str) -> str:
    """基于文件路径生成稳定的 file_id。"""
    return hashlib.md5(filepath.encode("utf-8")).hexdigest()


def compact_title_path(
    title_path: tuple[str, ...],
    *,
    max_depth: int = 3,
    max_item_chars: int = 120,
    max_total_chars: int = 256,
) -> tuple[str, ...]:
    """限制 title_path 深度与总长度，避免异常文档导致索引膨胀。"""
    compacted: list[str] = []
    total = 0
    for item in title_path[:max_depth]:
        clean = (item or "").strip()
        if not clean:
            continue
        if len(clean) > max_item_chars:
            clean = clean[:max_item_chars]
        if total + len(clean) > max_total_chars:
            remain = max_total_chars - total
            if remain <= 0:
                break
            clean = clean[:remain]
        compacted.append(clean)
        total += len(clean)
        if total >= max_total_chars:
            break
    return tuple(compacted)


def compact_title_path_for_settings(
    title_path: tuple[str, ...],
    settings: Settings | None = None,
) -> tuple[str, ...]:
    """按运行时配置压缩 title_path。"""
    normalized = settings or get_settings()
    return compact_title_path(
        title_path,
        max_depth=normalized.title_path_max_depth,
        max_item_chars=normalized.title_path_max_item_chars,
        max_total_chars=normalized.title_path_max_chars,
    )


def docs_to_indexed_chunks(
    filepath: str,
    source_type: str,
    docs: Iterable[Document],
    *,
    settings: Settings | None = None,
) -> list[IndexedChunk]:
    """将同一文件的 Document 列表转换为 IndexedChunk。"""
    normalized_settings = settings or get_settings()
    file_id = generate_file_id(filepath)
    chunks: list[IndexedChunk] = []
    counters: dict[str, int] = {}
    for doc in docs:
        meta = doc.metadata.copy()
        chunk_type = meta.get("chunk_type", "content")
        if chunk_type == "content":
            chunk_idx = meta.get("chunk_idx", 0)
            chunk_suffix = f"c{chunk_idx}"
        elif chunk_type == "filename":
            chunk_suffix = "fn"
        elif chunk_type == "heading":
            count = counters.get("heading", 0)
            chunk_suffix = f"h{count}"
            counters["heading"] = count + 1
        else:
            count = counters.get(chunk_type, 0)
            chunk_suffix = f"x{count}"
            counters[chunk_type] = count + 1

        chunk_id = f"{file_id}_{chunk_suffix}"
        filename = meta.pop("filename", "")
        filetype = meta.pop("type", "")
        title_path_list = meta.pop("title_path", [])
        title_path = tuple(title_path_list) if title_path_list else ()
        title_path = compact_title_path_for_settings(title_path, normalized_settings)
        meta.pop("chunk_type", None)
        doc_mtime = float(meta.pop("mtime", 0.0))
        ctime = float(meta.pop("ctime", 0.0))
        meta.pop("source", None)
        meta.pop("source_type", None)

        chunks.append(
            IndexedChunk(
                chunk_id=chunk_id,
                file_id=file_id,
                filepath=filepath,
                filename=filename,
                source_type=source_type,
                filetype=filetype,
                chunk_type=chunk_type,
                title_path=title_path,
                content=doc.page_content,
                embedding_text=doc.page_content,
                sparse_text=doc.page_content,
                chunk_index=meta.get("chunk_idx", 0),
                mtime=doc_mtime,
                ctime=ctime,
                metadata=meta,
            )
        )
    return chunks
