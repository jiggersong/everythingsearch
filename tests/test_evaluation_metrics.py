"""测试检索评测指标。"""

from __future__ import annotations

import pytest

from everythingsearch.evaluation.metrics import (
    CaseMetrics,
    aggregate_benchmark_metrics,
    calculate_case_metrics,
)


class TestEvaluationMetrics:
    """测试 TopK 与聚合指标。"""

    def test_calculate_case_metrics_scores_ranked_results(self):
        """应按相关文件位置计算 Top1、Recall、MRR 和 NDCG。"""
        metrics = calculate_case_metrics(
            ["/docs/other.md", "/docs/budget.xlsx", "/docs/notes.md"],
            {
                "/docs/budget.xlsx": 3,
                "/docs/notes.md": 1,
            },
        )

        assert metrics.top1_accuracy == 0.0
        assert metrics.recall_at_10 == 1.0
        assert metrics.recall_at_50 == 1.0
        assert metrics.mrr_at_10 == 0.5
        assert 0.0 < metrics.ndcg_at_10 < 1.0

    def test_calculate_case_metrics_handles_top1_hit(self):
        """首条相关时 Top1 与 MRR 都应满分。"""
        metrics = calculate_case_metrics(
            ["/docs/budget.xlsx", "/docs/other.md"],
            {"/docs/budget.xlsx": 3},
        )

        assert metrics.top1_accuracy == 1.0
        assert metrics.mrr_at_10 == 1.0
        assert metrics.ndcg_at_10 == 1.0

    def test_aggregate_benchmark_metrics_calculates_latency_percentiles(self):
        """聚合指标应包含平均质量指标与延迟分位数。"""
        aggregate = aggregate_benchmark_metrics(
            [
                CaseMetrics(1.0, 1.0, 1.0, 1.0, 1.0),
                CaseMetrics(0.0, 0.5, 1.0, 0.5, 0.75),
            ],
            [30.0, 10.0],
            rerank_fallback_count=1,
        )

        assert aggregate.case_count == 2
        assert aggregate.top1_accuracy == 0.5
        assert aggregate.recall_at_10 == 0.75
        assert aggregate.p50_latency_ms == 20.0
        assert aggregate.p95_latency_ms == 30.0
        assert aggregate.rerank_fallback_rate == pytest.approx(0.5)

    def test_aggregate_benchmark_metrics_rejects_latency_length_mismatch(self):
        """延迟列表须与用例一一对应。"""
        with pytest.raises(ValueError, match="latency_ms_values"):
            aggregate_benchmark_metrics(
                [CaseMetrics(1.0, 1.0, 1.0, 1.0, 1.0)],
                [10.0, 20.0],
            )

