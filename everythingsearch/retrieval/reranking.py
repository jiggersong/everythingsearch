"""重排模块。"""

from __future__ import annotations

import logging
from typing import Protocol

import dashscope

from everythingsearch.infra.settings import Settings, require_dashscope_api_key
from everythingsearch.retrieval.models import QueryPlan, SearchCandidate

logger = logging.getLogger(__name__)


class DocumentReranker(Protocol):
    """文档重排器协议。"""

    def rerank(self, plan: QueryPlan, candidates: list[SearchCandidate]) -> list[SearchCandidate]:
        """对候选文档进行重排序。"""


class DashScopeReranker:
    """基于 DashScope API 的文档重排器。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = settings.rerank_model
        self._top_n = settings.rerank_top_n

    def rerank(self, plan: QueryPlan, candidates: list[SearchCandidate]) -> list[SearchCandidate]:
        if not candidates:
            return []

        # BUG-012: 充分去重，避免 sparse 和 dense 召回的相同物理内容浪费 token
        seen_keys = set()
        deduped_candidates = []
        for c in candidates:
            # chunk_index 在 Metadata 里可能是 'chunk_idx'，如果在 model 里没直接映射好
            # 使用 content 前 50 个字符 + file_id 也能很好的去重
            content_prefix = (c.content or "")[:50]
            key = (c.file_id, content_prefix)
            if key not in seen_keys:
                seen_keys.add(key)
                deduped_candidates.append(c)

        # 截断输入候选集，避免超发
        candidates_to_rerank = deduped_candidates[:self._top_n]
        if not plan.normalized_query:
            return candidates_to_rerank

        try:
            # 构造输入 documents，包含上下文
            # 组合方式： [title_path] content，给 reranker 最充分的信息
            documents = []
            max_doc_chars = self._settings.rerank_max_doc_chars
            for c in candidates_to_rerank:
                path_str = " > ".join(c.title_path) if c.title_path else ""
                prefix = f"[{path_str}]\n" if path_str else ""
                content = c.content or ""
                # BUG-010: 稍微截断以防止单词条超长
                full_text = f"{prefix}{content}"
                if len(full_text) > max_doc_chars:
                    full_text = full_text[:max_doc_chars]
                documents.append(full_text)

            # 延迟获取 API Key，避免在进程启动时因缺少环境变量崩溃
            api_key = require_dashscope_api_key(self._settings)

            resp = dashscope.TextReRank.call(
                model=self._model,
                query=plan.normalized_query,
                documents=documents,
                api_key=api_key,
                top_n=len(documents),
                return_documents=False
            )

            if resp.status_code != 200:
                logger.warning(
                    "重排 API 返回非 200 状态码: %s, message: %s. 降级为原顺序返回。",
                    resp.status_code,
                    resp.message
                )
                return candidates_to_rerank

            results = resp.output.results
            # API 返回的结果是一个列表，每个元素包含 index (原始 documents 数组的索引), relevance_score
            # 我们按照返回的顺序重新排列 candidate，并注入分数
            
            reranked_candidates = []
            for rank, item in enumerate(results, start=1):
                # 如果 return_documents=False，index 在 item 上直接提供，而不是 item.document.index
                idx = getattr(item, "index", None)
                if idx is None and hasattr(item, "document") and item.document is not None:
                    idx = getattr(item.document, "index", None)
                
                if idx is None:
                    logger.warning("Rerank API 返回的项缺少 index: %s", item)
                    continue

                score = item.relevance_score
                
                orig_candidate = candidates_to_rerank[idx]
                
                # 新建一个 Candidate 实例填充 rerank_score 和 rerank_rank
                new_candidate = SearchCandidate(
                    chunk_id=orig_candidate.chunk_id,
                    file_id=orig_candidate.file_id,
                    filepath=orig_candidate.filepath,
                    filename=orig_candidate.filename,
                    chunk_type=orig_candidate.chunk_type,
                    content=orig_candidate.content,
                    title_path=orig_candidate.title_path,
                    source_type=orig_candidate.source_type,
                    filetype=orig_candidate.filetype,
                    sparse_rank=orig_candidate.sparse_rank,
                    dense_rank=orig_candidate.dense_rank,
                    sparse_score=orig_candidate.sparse_score,
                    dense_score=orig_candidate.dense_score,
                    fusion_score=orig_candidate.fusion_score,
                    rerank_rank=rank,
                    rerank_score=score,
                    metadata=orig_candidate.metadata
                )
                reranked_candidates.append(new_candidate)
                
            return reranked_candidates

        except Exception as exc:
            logger.warning("文档重排失败，触发降级策略 (原样返回): %s", exc)
            return candidates_to_rerank
