"""SearchPipeline 单元测试：端到端超时预算、高精度跳过重排、共享线程池。"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from everythingsearch.request_validation import SearchRequest
from everythingsearch.retrieval.models import (
    AggregatedResult,
    QueryPlan,
    SearchCandidate,
)
from everythingsearch.retrieval.pipeline import SearchPipeline


def _make_settings(timeout: float = 0.3) -> SimpleNamespace:
    return SimpleNamespace(
        search_timeout_seconds=timeout,
        score_threshold=0.01,
        default_search_limit=20,
    )


def _make_pipeline(timeout: float = 0.3) -> SearchPipeline:
    """绕过重型 __init__，仅装配测试所需字段。"""
    pipeline = SearchPipeline.__new__(SearchPipeline)
    pipeline._settings = _make_settings(timeout)
    pipeline._planner = MagicMock()
    pipeline._sparse_retriever = MagicMock()
    pipeline._dense_retriever = MagicMock()
    pipeline._fusion = MagicMock()
    pipeline._reranker = MagicMock()
    pipeline._aggregator = MagicMock()
    pipeline._embedding = None
    pipeline._executor = ThreadPoolExecutor(
        max_workers=2, thread_name_prefix="test-search-pipeline"
    )
    pipeline._rerank_executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="test-search-rerank"
    )
    return pipeline


def _make_candidate(cid: str, content: str = "x", file_id: str | None = None) -> SearchCandidate:
    return SearchCandidate(
        chunk_id=cid,
        file_id=file_id or f"f_{cid}",
        filepath=f"/t/{cid}",
        filename=cid,
        chunk_type="content",
        content=content,
        title_path=(),
        source_type="file",
        filetype=".txt",
        sparse_rank=None,
        dense_rank=None,
        sparse_score=None,
        dense_score=None,
        fusion_score=0.5,
        rerank_rank=None,
        rerank_score=None,
        metadata={},
    )


def _make_agg(cid: str) -> AggregatedResult:
    return AggregatedResult(
        file_id=f"f_{cid}",
        filename=cid,
        filepath=f"/t/{cid}",
        source_type="file",
        filetype=".txt",
        mtime=1.0,
        score=0.5,
        best_chunk_type="content",
        highlights=["h"],
        metadata={},
    )


def _make_plan(exactness_level: str = "medium", normalized_query: str = "q") -> QueryPlan:
    return QueryPlan(
        raw_query="test",
        normalized_query=normalized_query,
        sparse_query="",
        dense_query="",
        query_type="semantic",
        exactness_level=exactness_level,
        source_filter=None,
        date_field="mtime",
        date_from=None,
        date_to=None,
        sparse_top_k=10,
        dense_top_k=10,
        fusion_top_k=10,
        rerank_top_k=10,
    )


def _make_request(query: str = "q", exact_focus: bool = False) -> SearchRequest:
    return SearchRequest(
        query=query,
        source="all",
        date_field="mtime",
        date_from=None,
        date_to=None,
        limit=None,
        exact_focus=exact_focus,
    )


@pytest.fixture
def pipeline():
    p = _make_pipeline()
    yield p
    p.shutdown(wait=True)


class TestSearchPipelineTimeoutBudget:
    def test_rerank_respects_end_to_end_budget(self, pipeline):
        """重排超出剩余预算时应在预算内降级返回，不阻塞到重排真实耗时。"""
        pipeline._planner.plan.return_value = _make_plan(exactness_level="medium")
        pipeline._sparse_retriever.retrieve.return_value = []
        pipeline._dense_retriever.retrieve.return_value = []
        c1, c2 = _make_candidate("c1"), _make_candidate("c2")
        pipeline._fusion.fuse.return_value = [c1, c2]

        # 慢重排：耗时 0.5s，但预算仅 0.3s
        def slow_rerank(p, cands):
            time.sleep(0.5)
            return cands

        pipeline._reranker.rerank.side_effect = slow_rerank
        pipeline._aggregator.aggregate.return_value = [_make_agg("c1"), _make_agg("c2")]

        start = time.monotonic()
        results = pipeline.search(_make_request())
        elapsed = time.monotonic() - start

        # 必须早于慢重排的实际耗时（0.5s）返回，证明预算约束覆盖整段链路
        assert elapsed < 0.3 + 0.2
        assert pipeline._reranker.rerank.called
        assert len(results) == 2

        # 超时降级后候选必须保留融合顺序（rerank_score=None），
        # 从而走 RRF 阈值跳过逻辑（见 search() 中 5.5 节条件），不被误过滤。
        passed = pipeline._aggregator.aggregate.call_args[0][0]
        assert all(c.rerank_score is None for c in passed)

    def test_recall_then_rerank_uses_remaining_budget(self, pipeline):
        """召回很快完成时，剩余预算留给重排；重排慢则整体仍受预算约束。"""
        pipeline._planner.plan.return_value = _make_plan(exactness_level="medium")
        pipeline._sparse_retriever.retrieve.return_value = []
        pipeline._dense_retriever.retrieve.return_value = []
        pipeline._fusion.fuse.return_value = [_make_candidate("c1")]
        # 慢重排耗时 0.6s，预算 0.3s
        pipeline._reranker.rerank.side_effect = lambda p, cands: time.sleep(0.6) or cands
        pipeline._aggregator.aggregate.return_value = [_make_agg("c1")]

        start = time.monotonic()
        pipeline.search(_make_request())
        elapsed = time.monotonic() - start

        # 未等到 0.6s 重排完成即降级返回
        assert elapsed < 0.3 + 0.2


class TestSearchPipelineHighPrecisionSkipRerank:
    def test_high_exactness_skips_rerank(self, pipeline):
        """exactness_level=='high' 时不调用远程重排 API，结果仍正常聚合。"""
        pipeline._planner.plan.return_value = _make_plan(exactness_level="high")
        pipeline._sparse_retriever.retrieve.return_value = []
        pipeline._dense_retriever.retrieve.return_value = []
        c1, c2 = _make_candidate("c1"), _make_candidate("c2")
        pipeline._fusion.fuse.return_value = [c1, c2]
        pipeline._aggregator.aggregate.side_effect = (
            lambda cands, q, max_highlights=3: [_make_agg(c.chunk_id) for c in cands]
        )

        results = pipeline.search(_make_request(exact_focus=True))

        pipeline._reranker.rerank.assert_not_called()
        assert len(results) == 2

    def test_non_high_uses_rerank(self, pipeline):
        """非高精度场景仍执行重排，且重排结果透传至聚合。"""
        pipeline._planner.plan.return_value = _make_plan(exactness_level="medium")
        pipeline._sparse_retriever.retrieve.return_value = []
        pipeline._dense_retriever.retrieve.return_value = []
        c1, c2 = _make_candidate("c1"), _make_candidate("c2")
        pipeline._fusion.fuse.return_value = [c1, c2]
        # 重排返回反序
        pipeline._reranker.rerank.side_effect = lambda p, cands: list(reversed(cands))
        pipeline._aggregator.aggregate.side_effect = (
            lambda cands, q, max_highlights=3: [_make_agg(c.chunk_id) for c in cands]
        )

        pipeline.search(_make_request())

        pipeline._reranker.rerank.assert_called_once()
        passed = pipeline._aggregator.aggregate.call_args[0][0]
        assert [c.chunk_id for c in passed] == ["c2", "c1"]


class TestSearchPipelineSharedExecutor:
    def test_search_reuses_shared_executor(self, pipeline):
        """search() 不应在每次请求时新建线程池。"""
        pipeline._planner.plan.return_value = _make_plan(exactness_level="medium")
        pipeline._sparse_retriever.retrieve.return_value = []
        pipeline._dense_retriever.retrieve.return_value = []
        pipeline._fusion.fuse.return_value = [_make_candidate("c1")]
        pipeline._reranker.rerank.return_value = [_make_candidate("c1")]
        pipeline._aggregator.aggregate.side_effect = (
            lambda cands, q, max_highlights=3: [_make_agg(c.chunk_id) for c in cands]
        )
        req = _make_request()

        with patch("everythingsearch.retrieval.pipeline.ThreadPoolExecutor") as mock_tpe:
            pipeline.search(req)
            pipeline.search(req)
            # search() 内部不得再创建 ThreadPoolExecutor（应复用实例级 self._executor）
            assert mock_tpe.call_count == 0
        assert pipeline._executor is not None


class TestRerankExecutorIsolation:
    def test_rerank_uses_separate_pool_from_recall(self, pipeline):
        """重排提交到独立的 `_rerank_executor`，召回提交到 `_executor`（池隔离）。

        验证超时滞后时重排线程不会挤占召回池的并行度（见 Item 2 修复）。
        """
        pipeline._planner.plan.return_value = _make_plan(exactness_level="medium")
        pipeline._sparse_retriever.retrieve.return_value = []
        pipeline._dense_retriever.retrieve.return_value = []
        pipeline._fusion.fuse.return_value = [_make_candidate("c1")]
        pipeline._reranker.rerank.return_value = [_make_candidate("c1")]
        pipeline._aggregator.aggregate.side_effect = (
            lambda cands, q, max_highlights=3: [_make_agg(c.chunk_id) for c in cands]
        )

        recall_submits = []
        rerank_submits = []
        real_exec_submit = pipeline._executor.submit
        real_rerank_submit = pipeline._rerank_executor.submit

        def spy_exec(*a, **k):
            recall_submits.append(1)
            return real_exec_submit(*a, **k)

        def spy_rerank(*a, **k):
            rerank_submits.append(1)
            return real_rerank_submit(*a, **k)

        pipeline._executor.submit = spy_exec
        pipeline._rerank_executor.submit = spy_rerank

        pipeline.search(_make_request())

        # 召回阶段提交 sparse + dense 两次，均走召回池 _executor
        assert len(recall_submits) == 2
        # 重排阶段提交一次，走独立的 _rerank_executor
        assert len(rerank_submits) == 1
