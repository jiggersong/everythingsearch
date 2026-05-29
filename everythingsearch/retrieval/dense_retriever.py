"""稠密检索模块。"""

from __future__ import annotations

import json
import logging
from typing import Protocol

import chromadb
from langchain_chroma import Chroma

from everythingsearch.indexing.chunk_store import fetch_chunks_by_ids
from everythingsearch.indexing.dense_lifecycle import COLLECTION_NAME
from everythingsearch.infra.settings import Settings
from everythingsearch.retrieval.embedding import EmbeddingProvider
from everythingsearch.retrieval.models import QueryPlan, SearchCandidate

logger = logging.getLogger(__name__)


class DenseRetriever(Protocol):
    """稠密检索器协议。"""

    def retrieve(self, plan: QueryPlan) -> list[SearchCandidate]:
        """执行稠密检索并返回候选。"""


_chroma_client_cache = {}

def _get_chroma_client(persist_directory: str):
    """获取或初始化 ChromaDB Client（单例），避免重复实例化导致内存泄漏 (BUG-009)。"""
    import os
    path = os.path.abspath(persist_directory)
    if path not in _chroma_client_cache:
        _chroma_client_cache[path] = chromadb.PersistentClient(path=path)
    return _chroma_client_cache[path]

class ChromaDenseRetriever:
    """基于 ChromaDB 的稠密检索器。"""

    def __init__(self, settings: Settings, embedding: EmbeddingProvider) -> None:
        self._persist_directory = settings.persist_directory
        self._embedding = embedding
        self._collection_name = COLLECTION_NAME
        self._sparse_index_path = settings.sparse_index_path
        self._client = _get_chroma_client(self._persist_directory)

        # 封装的 Langchain Chroma 实例
        self._db = Chroma(
            client=self._client,
            collection_name=self._collection_name,
            embedding_function=self._embedding,
            collection_metadata={"hnsw:space": "cosine"}
        )

    def retrieve(self, plan: QueryPlan) -> list[SearchCandidate]:
        if not plan.dense_query.strip():
            return []

        try:
            # 构建过滤条件
            where_filter = {}
            if plan.source_filter:
                where_filter["source_type"] = plan.source_filter

            if plan.date_from is not None or plan.date_to is not None:
                # ChromaDB 目前对于复杂的多条件（AND/OR）支持有一些特定的语法，
                # 对于单个范围可以用 $gte, $lte
                date_conds = {}
                if plan.date_from is not None:
                    date_conds["$gte"] = plan.date_from
                if plan.date_to is not None:
                    date_conds["$lte"] = plan.date_to
                
                # 如果只有时间范围
                if date_conds:
                    where_filter[plan.date_field] = date_conds

            if plan.path_filter:
                path_cond = {
                    "$or": [
                        {"filepath": {"$contains": plan.path_filter}},
                        {"source": {"$contains": plan.path_filter}}
                    ]
                }
                if not where_filter:
                    where_filter = path_cond
                else:
                    # 如果原先已有过滤条件，将其与 path_cond 通过 $and 合并
                    # 注意：ChromaDB 中如果有多个不同键的等值过滤，通常直接平铺。
                    # 但如果有高级操作符，建议放入 $and 数组。
                    and_list = [path_cond]
                    for k, v in where_filter.items():
                        and_list.append({k: v})
                    where_filter = {"$and": and_list}
            
            filter_arg = where_filter if where_filter else None

            # similarity_search_with_score 返回 (Document, distance)
            # 在 hnsw:space="cosine" 时，distance 是 余弦距离 (0 到 2)
            results = self._db.similarity_search_with_score(
                query=plan.dense_query,
                k=plan.dense_top_k,
                filter=filter_arg,
            )

            chunk_ids: list[str] = []
            parsed_rows: list[tuple] = []
            for rank, (doc, distance) in enumerate(results, start=1):
                meta = doc.metadata.copy()
                chunk_id = meta.pop("chunk_id", "")
                if not chunk_id:
                    file_id = meta.get("file_id", str(hash(doc.page_content)))
                    chunk_idx = meta.get("chunk_idx", 0)
                    chunk_id = f"{file_id}_{chunk_idx}"
                chunk_ids.append(chunk_id)
                parsed_rows.append((rank, doc, distance, meta, chunk_id))

            chunk_records = fetch_chunks_by_ids(self._sparse_index_path, chunk_ids)

            candidates = []
            for rank, doc, distance, meta, chunk_id in parsed_rows:
                meta = meta.copy()

                # 提取基础字段
                chunk_id = meta.pop("chunk_id", chunk_id) or chunk_id
                file_id = meta.pop("file_id", "")
                filepath = meta.pop("filepath", meta.pop("source", ""))
                filename = meta.pop("filename", "")
                source_type = meta.pop("source_type", "file")
                filetype = meta.pop("filetype", meta.pop("type", ""))
                chunk_type = meta.pop("chunk_type", "content")
                
                title_path_str = meta.pop("title_path", "[]")
                try:
                    title_path = tuple(json.loads(title_path_str))
                except (TypeError, ValueError):
                    title_path = ()

                stored = chunk_records.get(chunk_id)
                if stored is not None:
                    content = stored.content
                    if stored.title_path:
                        title_path = stored.title_path
                else:
                    content = doc.page_content if doc.page_content.strip() else ""

                # 分数转换: 余弦距离转化为相似度 (1 - distance)
                # 这样就保证了值越大越相似（在 0~1 的范围内）
                dense_score = max(0.0, 1.0 - distance)

                candidates.append(SearchCandidate(
                    chunk_id=chunk_id,
                    file_id=file_id,
                    filepath=filepath,
                    filename=filename,
                    chunk_type=chunk_type,
                    content=content,
                    title_path=title_path,
                    source_type=source_type,
                    filetype=filetype,
                    sparse_rank=None,
                    dense_rank=rank,
                    sparse_score=None,
                    dense_score=dense_score,
                    fusion_score=0.0,
                    metadata=meta
                ))

            return candidates
        except Exception as exc:
            logger.error("稠密检索发生异常: %s", exc)
            return []
