"""稠密检索模块。"""

from __future__ import annotations

import logging
from typing import Protocol

import chromadb
from langchain_chroma import Chroma

from everythingsearch.infra.settings import Settings
from everythingsearch.retrieval.embedding import EmbeddingProvider
from everythingsearch.retrieval.models import QueryPlan, SearchCandidate

logger = logging.getLogger(__name__)


class DenseRetriever(Protocol):
    """稠密检索器协议。"""

    def retrieve(self, plan: QueryPlan) -> list[SearchCandidate]:
        """执行稠密检索并返回候选。"""


class ChromaDenseRetriever:
    """基于 ChromaDB 的稠密检索器。"""

    def __init__(self, settings: Settings, embedding: EmbeddingProvider) -> None:
        self._persist_directory = settings.persist_directory
        self._embedding = embedding
        self._collection_name = "local_files"
        self._client = chromadb.PersistentClient(path=self._persist_directory)

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

            candidates = []
            for rank, (doc, distance) in enumerate(results, start=1):
                meta = doc.metadata.copy()

                # 提取基础字段
                chunk_id = meta.pop("chunk_id", "")
                # 如果没有 chunk_id（旧版本直接用 Chroma 写可能没有），暂时造一个
                if not chunk_id:
                    # 兼容：旧数据没有写入 chunk_id 到 metadata，Langchain 有底层 id 但不在 metadata 里
                    # 我们暂不处理旧格式兼容，在后续全量索引重建时会带上 chunk_id。
                    # 或者用 file_id + chunk_idx 组合。
                    file_id = meta.get("file_id", str(hash(doc.page_content)))
                    chunk_idx = meta.get("chunk_idx", 0)
                    chunk_id = f"{file_id}_{chunk_idx}"

                file_id = meta.pop("file_id", "")
                filepath = meta.pop("filepath", meta.pop("source", ""))
                filename = meta.pop("filename", "")
                source_type = meta.pop("source_type", "file")
                filetype = meta.pop("filetype", meta.pop("type", ""))
                chunk_type = meta.pop("chunk_type", "content")
                
                title_path_str = meta.pop("title_path", "[]")
                try:
                    import json
                    title_path = tuple(json.loads(title_path_str))
                except (TypeError, ValueError):
                    title_path = ()

                # 分数转换: 余弦距离转化为相似度 (1 - distance)
                # 这样就保证了值越大越相似（在 0~1 的范围内）
                dense_score = max(0.0, 1.0 - distance)

                candidates.append(SearchCandidate(
                    chunk_id=chunk_id,
                    file_id=file_id,
                    filepath=filepath,
                    filename=filename,
                    chunk_type=chunk_type,
                    content=doc.page_content, # dense retriever 通常召回的就是 embedding_text 或者原始内容
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
