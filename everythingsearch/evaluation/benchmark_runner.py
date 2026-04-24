"""检索 benchmark runner。"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from time import perf_counter
from typing import Protocol

from everythingsearch.request_validation import SearchRequest

from .dataset import EvaluationCase, EvaluationDatasetError, load_evaluation_cases
from .metrics import BenchmarkMetrics, CaseMetrics, aggregate_benchmark_metrics, calculate_case_metrics


class BenchmarkSearchError(RuntimeError):
    """benchmark 搜索执行失败。"""


class Searcher(Protocol):
    """benchmark 使用的搜索器接口。"""

    def search(self, query: str, *, limit: int | None = None) -> list[dict]:
        """执行搜索并返回现有 API 结果格式。"""


@dataclass(frozen=True)
class CaseBenchmarkResult:
    """单条用例的 benchmark 结果。"""

    query: str
    query_type: str
    metrics: CaseMetrics
    latency_ms: float
    result_filepaths: tuple[str, ...]


@dataclass(frozen=True)
class BenchmarkReport:
    """完整 benchmark 报告。"""

    experiment: str
    dataset_path: str
    metrics: BenchmarkMetrics
    cases: tuple[CaseBenchmarkResult, ...]


class BaselineSearcher:
    """使用原生 search_core 的 baseline 搜索器（用于比对新旧架构差异）。"""

    def search(self, query: str, *, limit: int | None = None) -> list[dict]:
        """执行旧版词法检索。"""
        from everythingsearch.search import search_core
        results = search_core(
            query,
            source_filter="all",
            date_field="mtime",
            date_from=None,
            date_to=None,
            exact_focus=False,
        )
        if limit is not None:
            results = results[:limit]
            
        # 将 "file" 映射为 "filepath" 供 benchmark 抽取
        return [{"filepath": r.get("file", ""), **r} for r in results]


class PipelineSearcher:
    """使用新一代 SearchPipeline 的搜索器。"""

    def __init__(self):
        from everythingsearch.retrieval.pipeline import SearchPipeline
        self._pipeline = SearchPipeline()

    def search(self, query: str, *, limit: int | None = None) -> list[dict]:
        from everythingsearch.request_validation import SearchRequest
        
        request = SearchRequest(
            query=query,
            source="all",
            date_field="mtime",
            date_from=None,
            date_to=None,
            limit=limit,
        )
        results = self._pipeline.search(request)
        # 新版 pipeline search() 已经按照兼容格式返回，包含 "file"
        return [{"filepath": r.get("file", ""), **r} for r in results]


def run_benchmark(
    dataset_path: str | Path,
    searcher: Searcher,
    *,
    experiment: str = "baseline_current",
    limit: int = 50,
) -> BenchmarkReport:
    """运行检索 benchmark。"""
    cases = load_evaluation_cases(dataset_path)
    case_results: list[CaseBenchmarkResult] = []
    case_metrics: list[CaseMetrics] = []
    latency_ms_values: list[float] = []

    for case in cases:
        case_result = _run_case(case, searcher, limit=limit)
        case_results.append(case_result)
        case_metrics.append(case_result.metrics)
        latency_ms_values.append(case_result.latency_ms)

    # rerank 未接入前显式传 0，与 §17.2 RerankFallbackRate 定义一致；接入后由调用方汇总降级次数。
    aggregate = aggregate_benchmark_metrics(
        case_metrics,
        latency_ms_values,
        rerank_fallback_count=0,
    )
    return BenchmarkReport(
        experiment=experiment,
        dataset_path=str(dataset_path),
        metrics=aggregate,
        cases=tuple(case_results),
    )


def report_to_dict(report: BenchmarkReport, *, include_cases: bool = True) -> dict:
    """将 benchmark 报告转换为 JSON 可序列化字典。"""
    payload = {
        "experiment": report.experiment,
        "dataset_path": report.dataset_path,
        "metrics": asdict(report.metrics),
    }
    if include_cases:
        payload["cases"] = [
            {
                "query": item.query,
                "query_type": item.query_type,
                "metrics": asdict(item.metrics),
                "latency_ms": item.latency_ms,
                "result_filepaths": list(item.result_filepaths),
            }
            for item in report.cases
        ]
    return payload


def _run_case(case: EvaluationCase, searcher: Searcher, *, limit: int) -> CaseBenchmarkResult:
    start = perf_counter()
    try:
        results = searcher.search(case.query, limit=limit)
    except (RuntimeError, ValueError, OSError) as exc:
        import logging
        logging.error(f"评测用例执行异常 (query='%s'): %s", case.query, exc)
        elapsed_ms = (perf_counter() - start) * 1000
        return CaseBenchmarkResult(
            query=case.query,
            query_type=case.query_type,
            metrics=CaseMetrics(
                top1_accuracy=0.0,
                recall_at_10=0.0,
                recall_at_50=0.0,
                mrr_at_10=0.0,
                ndcg_at_10=0.0,
            ),
            latency_ms=elapsed_ms,
            result_filepaths=(),
        )
    elapsed_ms = (perf_counter() - start) * 1000

    result_filepaths = _extract_result_filepaths(results)
    metrics = calculate_case_metrics(
        result_filepaths,
        case.relevance_by_filepath,
    )
    return CaseBenchmarkResult(
        query=case.query,
        query_type=case.query_type,
        metrics=metrics,
        latency_ms=elapsed_ms,
        result_filepaths=tuple(result_filepaths),
    )


def _extract_result_filepaths(results: list[dict]) -> list[str]:
    filepaths: list[str] = []
    seen: set[str] = set()
    for result in results:
        filepath = result.get("filepath")
        if not isinstance(filepath, str) or not filepath:
            continue
        if filepath in seen:
            continue
        seen.add(filepath)
        filepaths.append(filepath)
    return filepaths


def main() -> int:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="运行 EverythingSearch 检索 benchmark")
    parser.add_argument("dataset", help="JSONL 评测数据集路径")
    parser.add_argument("--experiment", default="baseline_current", help="实验名称")
    parser.add_argument("--limit", type=int, default=50, help="每条查询返回结果上限")
    parser.add_argument("--no-cases", action="store_true", help="仅输出聚合指标")
    parser.add_argument("--engine", choices=["baseline", "pipeline"], default="baseline", help="使用的检索引擎")
    args = parser.parse_args()

    try:
        if args.engine == "pipeline":
            from everythingsearch.infra.settings import get_settings, apply_sdk_environment
            apply_sdk_environment(get_settings())
            searcher = PipelineSearcher()
        else:
            searcher = BaselineSearcher()
            
        report = run_benchmark(
            args.dataset,
            searcher,
            experiment=args.experiment,
            limit=args.limit,
        )
    except (EvaluationDatasetError, BenchmarkSearchError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps(report_to_dict(report, include_cases=not args.no_cases), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
