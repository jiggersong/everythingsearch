"""测试 benchmark runner。"""

from __future__ import annotations

from everythingsearch.evaluation.benchmark_runner import (
    report_to_dict,
    run_benchmark,
)


class FakeSearcher:
    """可控搜索器，用于测试 benchmark 编排。"""

    def __init__(self):
        self.calls: list[tuple[str, int | None]] = []

    def search(self, query: str, *, limit: int | None = None) -> list[dict]:
        self.calls.append((query, limit))
        if query == "预算 excel":
            return [
                {"filepath": "/docs/other.md"},
                {"filepath": "/docs/budget.xlsx"},
                {"filepath": "/docs/budget.xlsx"},
            ]
        return [{"filepath": "/docs/notes.md"}]


class TestBenchmarkRunner:
    """测试 benchmark runner 行为。"""

    def test_run_benchmark_uses_searcher_and_deduplicates_filepaths(self, tmp_path):
        """runner 应调用搜索器、去重结果路径并输出聚合指标。"""
        dataset_path = tmp_path / "search_eval.jsonl"
        dataset_path.write_text(
            '{"query":"预算 excel","query_type":"hybrid",'
            '"relevant_files":[{"filepath":"/docs/budget.xlsx","grade":3}]}\n'
            '{"query":"会议纪要","query_type":"semantic",'
            '"relevant_files":[{"filepath":"/docs/notes.md","grade":2}]}\n',
            encoding="utf-8",
        )
        searcher = FakeSearcher()

        report = run_benchmark(dataset_path, searcher, experiment="fake", limit=10)

        assert searcher.calls == [("预算 excel", 10), ("会议纪要", 10)]
        assert report.experiment == "fake"
        assert report.metrics.case_count == 2
        assert report.metrics.recall_at_10 == 1.0
        assert report.cases[0].result_filepaths == ("/docs/other.md", "/docs/budget.xlsx")

    def test_report_to_dict_can_omit_cases(self, tmp_path):
        """报告序列化支持只输出聚合指标。"""
        dataset_path = tmp_path / "search_eval.jsonl"
        dataset_path.write_text(
            '{"query":"会议纪要","query_type":"semantic",'
            '"relevant_files":[{"filepath":"/docs/notes.md","grade":2}]}\n',
            encoding="utf-8",
        )

        report = run_benchmark(dataset_path, FakeSearcher(), experiment="fake")
        payload = report_to_dict(report, include_cases=False)

        assert payload["experiment"] == "fake"
        assert "metrics" in payload
        assert "cases" not in payload
