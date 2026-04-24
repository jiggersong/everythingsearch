"""检索评测工具包。"""

from everythingsearch.evaluation.benchmark_runner import (
    BaselineSearcher,
    BenchmarkReport,
    CaseBenchmarkResult,
    run_benchmark,
    report_to_dict,
)
from everythingsearch.evaluation.dataset import (
    EvaluationCase,
    EvaluationDatasetError,
    RelevantFile,
    load_evaluation_cases,
)
from everythingsearch.evaluation.metrics import (
    BenchmarkMetrics,
    CaseMetrics,
    aggregate_benchmark_metrics,
    calculate_case_metrics,
)

__all__ = [
    "aggregate_benchmark_metrics",
    "BaselineSearcher",
    "BenchmarkMetrics",
    "BenchmarkReport",
    "calculate_case_metrics",
    "CaseBenchmarkResult",
    "CaseMetrics",
    "EvaluationCase",
    "EvaluationDatasetError",
    "load_evaluation_cases",
    "RelevantFile",
    "report_to_dict",
    "run_benchmark",
]
