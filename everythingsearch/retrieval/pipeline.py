"""主搜索管线模块。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any

from everythingsearch.infra.settings import Settings, get_settings
from everythingsearch.request_validation import SearchRequest
from everythingsearch.retrieval.aggregation import DefaultFileAggregator
from everythingsearch.retrieval.dense_retriever import ChromaDenseRetriever
from everythingsearch.retrieval.embedding import DashScopeEmbeddingProvider
from everythingsearch.retrieval.fusion import RRFCandidateFusion
from everythingsearch.retrieval.query_planner import DefaultQueryPlanner
from everythingsearch.retrieval.reranking import DashScopeReranker
from everythingsearch.retrieval.sparse_retriever import SQLiteSparseRetriever

logger = logging.getLogger(__name__)


class SearchPipeline:
    """完整的高精度多路召回搜索管线。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

        self._planner = DefaultQueryPlanner()
        self._embedding = DashScopeEmbeddingProvider(self._settings)

        # 召回层
        self._sparse_retriever = SQLiteSparseRetriever(self._settings)
        self._dense_retriever = ChromaDenseRetriever(self._settings, self._embedding)

        # 融合与重排层
        self._fusion = RRFCandidateFusion(self._settings)
        self._reranker = DashScopeReranker(self._settings)

        # 聚合层
        self._aggregator = DefaultFileAggregator()

    def search(self, request: SearchRequest) -> list[dict[str, Any]]:
        """执行完整搜索链路，并返回兼容旧 API 的字典列表。"""
        # 1. 意图理解与规划
        plan = self._planner.plan(request)
        logger.info("Search QueryPlan: %s", plan)

        # 2. 多路召回 (并发执行)
        executor = ThreadPoolExecutor(max_workers=2)
        try:
            future_sparse = executor.submit(self._sparse_retriever.retrieve, plan)
            
            # 如果是强精确匹配，则跳过 Dense 召回以避免返回仅语义相近但无对应关键字的噪音
            if plan.exactness_level == "high":
                future_dense = executor.submit(lambda: [])
            else:
                future_dense = executor.submit(self._dense_retriever.retrieve, plan)

            timeout_sec = self._settings.search_timeout_seconds
            done, not_done = wait([future_sparse, future_dense], timeout=timeout_sec)
            
            for f in not_done:
                f.cancel()
            
            sparse_candidates = []
            if future_sparse in done:
                try:
                    sparse_candidates = future_sparse.result()
                except Exception as e:
                    logger.error("Sparse retrieval failed: %s", e)
            else:
                logger.warning("Sparse retrieval timed out after %ds", timeout_sec)
                
            dense_candidates = []
            if future_dense in done:
                try:
                    dense_candidates = future_dense.result()
                except Exception as e:
                    logger.error("Dense retrieval failed: %s", e)
            else:
                logger.warning("Dense retrieval timed out after %ds", timeout_sec)
        finally:
            executor.shutdown(wait=False)

        logger.info(
            "Recall: sparse=%d, dense=%d", len(sparse_candidates), len(dense_candidates)
        )

        # 3. 融合 (RRF)
        fused_candidates = self._fusion.fuse(sparse_candidates, dense_candidates, plan)
        logger.info("Fusion: %d candidates after RRF", len(fused_candidates))

        # 4. 重排 (Rerank)
        # Reranker 内部包含截断和异常降级逻辑
        reranked_candidates = self._reranker.rerank(plan, fused_candidates)

        # 5. 聚合为文件级结果
        aggregated_results = self._aggregator.aggregate(
            reranked_candidates, plan.normalized_query, max_highlights=3
        )

        # 5.5 按分数阈值过滤低质结果
        # 仅重排成功（rerank_score 有值）时生效；重排降级时融合分（RRF）量级远小于 1，
        # 硬套同一阈值会导致结果骤减甚至为空，因此降级路径跳过阈值过滤。
        if any(c.rerank_score is not None for c in reranked_candidates):
            score_threshold = self._settings.score_threshold
            aggregated_results = [r for r in aggregated_results if r.score >= score_threshold]

        # 6. 截断到最终要求的返回数 (默认或受限于 API request.limit)
        limit = request.limit if request.limit else self._settings.default_search_limit
        final_results = aggregated_results[:limit]

        # 转换为兼容的字典列表输出
        output = []
        for res in final_results:
            # 兼容老前端需要的一些特定字段
            tag = "精确匹配" if plan.exactness_level == "high" else "语义匹配"
            # relevance 原逻辑：关键词命中 or "x%"
            relevance = "关键词命中" if plan.exactness_level == "high" else f"{min(100, round(res.score * 100))}%"

            output.append(
                {
                    "filename": res.filename,
                    "filepath": res.filepath,
                    "relevance": relevance,
                    "tag": tag,
                    "preview": "\n... ".join(res.highlights),
                    "filetype": res.filetype,
                    "mtime": res.mtime,
                    "ctime": float(res.metadata.get("ctime", 0.0)),
                    "source_type": res.source_type,
                    "categories": res.metadata.get("categories", ""),
                    # 保留 Pipeline 特定字段
                    "file": res.filepath,
                    "score": res.score,
                    "metadata": {
                        "filename": res.filename,
                        "source": res.filepath,
                        "type": res.filetype,
                        "source_type": res.source_type,
                        "mtime": res.mtime,
                        "chunk_type": res.best_chunk_type,
                        **res.metadata,
                    },
                    "content": "\n... ".join(res.highlights),
                    "file_id": res.file_id,
                }
            )

        return output
