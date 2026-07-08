"""主搜索管线模块。"""

from __future__ import annotations

import logging
import time
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
from everythingsearch.retrieval.models import QueryPlan, SearchCandidate
from everythingsearch.retrieval.sparse_retriever import SQLiteSparseRetriever

logger = logging.getLogger(__name__)


def _build_relevance(score: float, exactness_level: str) -> str:
    """根据聚合分数和精确度级别计算展示用匹配度字符串。"""
    if exactness_level == "high":
        return "关键词命中"
    return f"{min(100, round(score * 100))}%"


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

        # 召回线程池：实例级复用、跨请求共享，仅用于稀疏/稠密召回。
        # 不在每次请求时创建/销毁，减少线程开销；进程退出时统一 shutdown（见 shutdown / Gunicorn worker_exit）。
        self._executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="search-pipeline",
        )

        # 重排线程池：与召回池隔离的独立 ThreadPoolExecutor(max_workers=1)。
        # 原因：重排是远程 DashScope 调用，可能超过端到端预算而超时降级。
        # 超时后线程无法被 cancel() 停止（见 _rerank_with_timeout 注释），仍会占用一个 slot
        # 直到 API 返回；若与召回池共用，则该占用会挤占后续请求的召回并行度（降为 1）。
        # 隔离后即便重排线程滞后，也不会饿死召回池。
        self._rerank_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="search-rerank",
        )

    def shutdown(self, wait: bool = False) -> None:
        """释放搜索线程池（召回池与重排池）。

        应在进程/worker 退出时调用（如 Gunicorn ``worker_exit`` 钩子），
        避免线程泄漏。``cancel_futures`` 会尝试取消尚未开始的任务。
        """
        for ex in (self._executor, self._rerank_executor):
            try:
                ex.shutdown(wait=wait, cancel_futures=True)
            except TypeError:
                # Python < 3.9 的 ThreadPoolExecutor.shutdown 不支持 cancel_futures
                ex.shutdown(wait=wait)

    def search(self, request: SearchRequest) -> list[dict[str, Any]]:
        """执行完整搜索链路，并返回兼容旧 API 的字典列表。"""
        # 1. 意图理解与规划
        plan = self._planner.plan(request)
        logger.info("Search QueryPlan: %s", plan)

        # 端到端超时预算：召回 + 重排 共享同一时间盒（SEARCH_TIMEOUT_SECONDS）。
        # 不再仅约束召回阶段，避免重排远程调用在预算外无限阻塞 sync worker。
        deadline = time.monotonic() + self._settings.search_timeout_seconds

        # 2. 多路召回 (并发执行，复用实例级线程池)
        future_sparse = self._executor.submit(self._sparse_retriever.retrieve, plan)

        # 如果是强精确匹配，则跳过 Dense 召回以避免返回仅语义相近但无对应关键字的噪音
        if plan.exactness_level == "high":
            future_dense = self._executor.submit(lambda: [])
        else:
            future_dense = self._executor.submit(self._dense_retriever.retrieve, plan)

        remaining = max(0.0, deadline - time.monotonic())
        done, not_done = wait([future_sparse, future_dense], timeout=remaining)

        for f in not_done:
            f.cancel()

        sparse_candidates = []
        if future_sparse in done:
            try:
                sparse_candidates = future_sparse.result()
            except Exception as e:
                logger.error("Sparse retrieval failed: %s", e)
        else:
            logger.warning(
                "Sparse retrieval exceeded timeout budget (limit=%.1fs)",
                self._settings.search_timeout_seconds,
            )

        dense_candidates = []
        if future_dense in done:
            try:
                dense_candidates = future_dense.result()
            except Exception as e:
                logger.error("Dense retrieval failed: %s", e)
        else:
            logger.warning(
                "Dense retrieval exceeded timeout budget (limit=%.1fs)",
                self._settings.search_timeout_seconds,
            )

        logger.info(
            "Recall: sparse=%d, dense=%d", len(sparse_candidates), len(dense_candidates)
        )

        # 3. 融合 (RRF)
        fused_candidates = self._fusion.fuse(sparse_candidates, dense_candidates, plan)
        logger.info("Fusion: %d candidates after RRF", len(fused_candidates))

        # 4. 重排 (Rerank)
        # 高精度关键词场景跳过重排 API：延迟稳定、无额外成本，且与原有关键词命中语义一致。
        if plan.exactness_level == "high":
            reranked_candidates = fused_candidates
        else:
            reranked_candidates = self._rerank_with_timeout(plan, fused_candidates, deadline)

        # 5. 聚合为文件级结果
        aggregated_results = self._aggregator.aggregate(
            reranked_candidates, plan.normalized_query, max_highlights=3
        )

        # 5.5 按分数阈值过滤低质结果
        # 仅重排成功（rerank_score 有值）时生效；重排降级/跳过时融合分（RRF）量级远小于 1，
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
            relevance = _build_relevance(res.score, plan.exactness_level)

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

    def _rerank_with_timeout(
        self,
        plan: QueryPlan,
        fused_candidates: list[SearchCandidate],
        deadline: float,
    ) -> list[SearchCandidate]:
        """在端到端超时预算内执行重排。

        超时或异常时降级为融合顺序（``rerank_score=None``），不抛出、不阻塞。
        与现有「重排 API 异常 -> 原序降级」保持一致的体验。

        已知 trade-off（重要，避免被误判为 bug 反复修复）：
        ``future.cancel()`` 只能取消**尚未开始**的任务，**无法中断已在线程中运行**
        的 DashScope 重排调用。因此在超时时：
          1) 即便已降级返回，底层重排线程仍可能继续向 DashScope 发送/等待响应，
             产生少量额外 API 费用，直到其自身完成；
          2) 该线程在结束前会占用 ``_rerank_executor`` 的一个 slot。
        由于重排池已与召回池（``_executor``）隔离，滞后线程**不会饿死后续请求**
        的召回并行度。若要彻底消除滞后开销，可评估 DashScope SDK 是否支持请求级
        超时，或在 SDK 调用外层套一个可被中断的取消机制（均不在本次范围内）。
        """
        if not fused_candidates:
            return []

        remaining = max(0.0, deadline - time.monotonic())
        if remaining <= 0:
            logger.warning("Rerank skipped: timeout budget exhausted")
            return fused_candidates

        future_rerank = self._rerank_executor.submit(
            self._reranker.rerank, plan, fused_candidates
        )
        done, not_done = wait([future_rerank], timeout=remaining)
        if not done:
            logger.warning(
                "Rerank exceeded timeout budget (%.1fs), falling back to fused order",
                remaining,
            )
            for f in not_done:
                f.cancel()
            return fused_candidates

        try:
            return future_rerank.result()
        except Exception as e:
            logger.error("Rerank failed: %s", e)
            return fused_candidates
