"""检索评测指标计算。"""

from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import median


@dataclass(frozen=True)
class CaseMetrics:
    """单条查询的评测指标。"""

    top1_accuracy: float
    recall_at_10: float
    recall_at_50: float
    mrr_at_10: float
    ndcg_at_10: float


@dataclass(frozen=True)
class BenchmarkMetrics:
    """评测集聚合指标。"""

    case_count: int
    top1_accuracy: float
    recall_at_10: float
    recall_at_50: float
    mrr_at_10: float
    ndcg_at_10: float
    p50_latency_ms: float
    p95_latency_ms: float
    rerank_fallback_rate: float


def calculate_case_metrics(
    result_filepaths: list[str],
    relevance_by_filepath: dict[str, int],
) -> CaseMetrics:
    """计算单条查询的 Top1、Recall、MRR 与 NDCG。"""
    relevant = {path: grade for path, grade in relevance_by_filepath.items() if grade > 0}
    if not relevant:
        return CaseMetrics(
            top1_accuracy=0.0,
            recall_at_10=0.0,
            recall_at_50=0.0,
            mrr_at_10=0.0,
            ndcg_at_10=0.0,
        )

    top1_accuracy = 1.0 if result_filepaths and relevant.get(result_filepaths[0], 0) > 0 else 0.0
    return CaseMetrics(
        top1_accuracy=top1_accuracy,
        recall_at_10=_recall_at_k(result_filepaths, relevant, 10),
        recall_at_50=_recall_at_k(result_filepaths, relevant, 50),
        mrr_at_10=_mrr_at_k(result_filepaths, relevant, 10),
        ndcg_at_10=_ndcg_at_k(result_filepaths, relevance_by_filepath, 10),
    )


def aggregate_benchmark_metrics(
    case_metrics: list[CaseMetrics],
    latency_ms_values: list[float],
    rerank_fallback_count: int = 0,
) -> BenchmarkMetrics:
    """聚合评测集指标。"""
    if not case_metrics:
        return BenchmarkMetrics(
            case_count=0,
            top1_accuracy=0.0,
            recall_at_10=0.0,
            recall_at_50=0.0,
            mrr_at_10=0.0,
            ndcg_at_10=0.0,
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
            rerank_fallback_rate=0.0,
        )

    if latency_ms_values and len(latency_ms_values) != len(case_metrics):
        raise ValueError(
            "latency_ms_values 长度须与 case_metrics 一致（逐条查询一条延迟）"
        )

    case_count = len(case_metrics)
    return BenchmarkMetrics(
        case_count=case_count,
        top1_accuracy=_mean([item.top1_accuracy for item in case_metrics]),
        recall_at_10=_mean([item.recall_at_10 for item in case_metrics]),
        recall_at_50=_mean([item.recall_at_50 for item in case_metrics]),
        mrr_at_10=_mean([item.mrr_at_10 for item in case_metrics]),
        ndcg_at_10=_mean([item.ndcg_at_10 for item in case_metrics]),
        p50_latency_ms=_percentile(latency_ms_values, 50),
        p95_latency_ms=_percentile(latency_ms_values, 95),
        rerank_fallback_rate=rerank_fallback_count / case_count,
    )


def _recall_at_k(result_filepaths: list[str], relevant: dict[str, int], k: int) -> float:
    hits = {path for path in result_filepaths[:k] if relevant.get(path, 0) > 0}
    return len(hits) / len(relevant)


def _mrr_at_k(result_filepaths: list[str], relevant: dict[str, int], k: int) -> float:
    for index, filepath in enumerate(result_filepaths[:k], start=1):
        if relevant.get(filepath, 0) > 0:
            return 1.0 / index
    return 0.0


def _ndcg_at_k(result_filepaths: list[str], relevance_by_filepath: dict[str, int], k: int) -> float:
    dcg = 0.0
    for index, filepath in enumerate(result_filepaths[:k], start=1):
        grade = max(0, relevance_by_filepath.get(filepath, 0))
        dcg += _dcg_gain(grade, index)

    ideal_grades = sorted((grade for grade in relevance_by_filepath.values() if grade > 0), reverse=True)
    ideal_dcg = sum(_dcg_gain(grade, index) for index, grade in enumerate(ideal_grades[:k], start=1))
    if ideal_dcg == 0:
        return 0.0
    return dcg / ideal_dcg


def _dcg_gain(grade: int, rank: int) -> float:
    return (2**grade - 1) / math.log2(rank + 1)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if percentile == 50:
        return float(median(values))
    ordered = sorted(values)
    index = math.ceil((percentile / 100) * len(ordered)) - 1
    bounded_index = max(0, min(index, len(ordered) - 1))
    return float(ordered[bounded_index])

