"""测试检索评测数据集加载。"""

from __future__ import annotations

import pytest

from everythingsearch.evaluation.dataset import (
    EvaluationDatasetError,
    load_evaluation_cases,
)


class TestEvaluationDataset:
    """测试 JSONL 评测数据集。"""

    def test_load_evaluation_cases_skips_blank_and_comment_lines(self, tmp_path):
        """应加载有效 JSONL，并跳过空行和注释行。"""
        dataset_path = tmp_path / "search_eval.jsonl"
        dataset_path.write_text(
            "\n"
            "# comment\n"
            '{"query":"预算 excel","query_type":"hybrid",'
            '"relevant_files":[{"filepath":"/docs/budget.xlsx","grade":3}],'
            '"must_include":["预算"],"notes":"预算查询"}\n',
            encoding="utf-8",
        )

        cases = load_evaluation_cases(dataset_path)

        assert len(cases) == 1
        assert cases[0].query == "预算 excel"
        assert cases[0].query_type == "hybrid"
        assert cases[0].relevance_by_filepath == {"/docs/budget.xlsx": 3}
        assert cases[0].must_include == ("预算",)
        assert cases[0].notes == "预算查询"

    def test_load_evaluation_cases_rejects_empty_dataset(self, tmp_path):
        """空数据集应报错，避免误跑出全 0 指标。"""
        dataset_path = tmp_path / "empty.jsonl"
        dataset_path.write_text("\n# comment\n", encoding="utf-8")

        with pytest.raises(EvaluationDatasetError, match="评测数据集为空"):
            load_evaluation_cases(dataset_path)

    def test_load_evaluation_cases_rejects_duplicate_relevant_file(self, tmp_path):
        """同一用例不允许重复标注同一路径。"""
        dataset_path = tmp_path / "duplicate.jsonl"
        dataset_path.write_text(
            '{"query":"预算","query_type":"exact",'
            '"relevant_files":['
            '{"filepath":"/docs/budget.xlsx","grade":3},'
            '{"filepath":"/docs/budget.xlsx","grade":2}'
            ']}\n',
            encoding="utf-8",
        )

        with pytest.raises(EvaluationDatasetError, match="重复 filepath"):
            load_evaluation_cases(dataset_path)

    def test_load_evaluation_cases_rejects_invalid_grade(self, tmp_path):
        """相关性等级只允许 0..3。"""
        dataset_path = tmp_path / "bad_grade.jsonl"
        dataset_path.write_text(
            '{"query":"预算","query_type":"exact",'
            '"relevant_files":[{"filepath":"/docs/budget.xlsx","grade":4}]}\n',
            encoding="utf-8",
        )

        with pytest.raises(EvaluationDatasetError, match="grade 必须是 0..3"):
            load_evaluation_cases(dataset_path)

    def test_load_evaluation_cases_rejects_only_zero_grades(self, tmp_path):
        """须至少一条 grade > 0，避免全零静默指标。"""
        dataset_path = tmp_path / "all_zero.jsonl"
        dataset_path.write_text(
            '{"query":"预算","query_type":"exact",'
            '"relevant_files":['
            '{"filepath":"/docs/a.xlsx","grade":0},'
            '{"filepath":"/docs/b.xlsx","grade":0}'
            ']}\n',
            encoding="utf-8",
        )

        with pytest.raises(EvaluationDatasetError, match="至少包含一条 grade > 0"):
            load_evaluation_cases(dataset_path)

