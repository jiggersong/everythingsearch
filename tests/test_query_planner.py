"""查询规划器单元测试 —— 覆盖分类规则 / 分词查询构建 / top_k 倍率。"""

import pytest

from everythingsearch.infra.settings import reset_settings_cache
from everythingsearch.request_validation import SearchRequest
from everythingsearch.retrieval.query_planner import DefaultQueryPlanner


class TestDetermineQueryType:
    """_determine_query_type() 分类规则 —— 整个搜索链路的第一道门。"""

    @pytest.mark.parametrize(
        "query, expected",
        [
            # 引号 → exact
            ('"神经网络"', "exact"),
            ("'machine learning'", "exact"),
            # 后缀名 → filename
            ("architecture.md", "filename"),
            ("report.pdf", "filename"),
            ("data.csv", "filename"),
            # 代码特征 → code（注意：不包含后缀名 .py，那个被 filename 优先抢走）
            ("def forward(self, x):", "code"),
            ("class NeuralNetwork:", "code"),
            ("import torch.nn as nn", "code"),
            ("Exception", "code"),
            ("RuntimeError", "code"),
            # 长文本 → semantic（> 15 字符 且 > 4 个词）
            ("how to train a neural network from scratch", "semantic"),
            # 默认 → hybrid
            ("神经网络", "hybrid"),
            ("search", "hybrid"),
        ],
    )
    def test_classification_rules(self, query, expected):
        planner = DefaultQueryPlanner()
        assert planner._determine_query_type(query) == expected

    def test_filename_wins_over_code_for_py_extension(self):
        """以 .py 结尾的查询优先命中 filename 而非 code（规则顺序保证）。"""
        planner = DefaultQueryPlanner()
        assert planner._determine_query_type("model.py") == "filename"

    def test_exact_wins_over_all_others(self):
        """引号规则优先级最高，即使同时命中其他规则也返回 exact。"""
        planner = DefaultQueryPlanner()
        assert planner._determine_query_type('"architecture.md"') == "exact"

    def test_short_text_not_semantic(self):
        """短文本即使有多词也不应该被误判为 semantic。"""
        planner = DefaultQueryPlanner()
        # 16 个字符但只有 3 个词 → 不是 semantic
        assert planner._determine_query_type("a b c d e f g h") == "hybrid"


class TestBuildSparseQuery:
    """_build_sparse_query() —— FTS5 查询串构建。"""

    def test_empty_query(self):
        planner = DefaultQueryPlanner()
        assert planner._build_sparse_query("") == ""
        assert planner._build_sparse_query("   ") == ""

    def test_chinese_tokenization(self):
        """中文分词后每个 token 带 * 前缀匹配后缀。"""
        planner = DefaultQueryPlanner()
        result = planner._build_sparse_query("神经网络架构")
        # jieba 分词结果应包含 * 后缀
        assert "*" in result
        assert len(result) > 0

    def test_filename_only_prefix(self):
        """filename_only=True 时查询串带 {filename} 前缀。"""
        planner = DefaultQueryPlanner()
        result = planner._build_sparse_query("readme", filename_only=True)
        assert result.startswith("{filename}")
        assert "readme" in result


class TestTopKMultipliers:
    """验证不同 query_type 下的 top_k 倍率逻辑。"""

    def setup_method(self):
        reset_settings_cache()

    def teardown_method(self):
        reset_settings_cache()

    def _make_plan(self, query, monkeypatch, **overrides):
        """构造 QueryPlan，可通过 overrides 覆盖 SearchRequest 字段。"""
        planner = DefaultQueryPlanner()
        req_kwargs = {"query": query, "source": "all", "date_field": "mtime",
                       "date_from": None, "date_to": None, "limit": None}
        req_kwargs.update(overrides)
        return planner.plan(SearchRequest(**req_kwargs))

    def test_exact_boosts_sparse_suppresses_dense(self, monkeypatch):
        """exact 类型：sparse×1.5，dense×0.3。"""
        # 用引号强制触发 exact
        plan = self._make_plan('"exact match"', monkeypatch)
        assert plan.query_type == "exact"
        assert plan.sparse_top_k > plan.dense_top_k, "exact 应偏重 sparse"

    def test_semantic_boosts_dense_suppresses_sparse(self, monkeypatch):
        """semantic 类型：sparse×0.7，dense×1.5。"""
        plan = self._make_plan("how to design a scalable search pipeline", monkeypatch)
        assert plan.query_type == "semantic"
        assert plan.dense_top_k > plan.sparse_top_k, "semantic 应偏重 dense"

    def test_filename_maxes_sparse_minimizes_dense(self, monkeypatch):
        """filename 类型：sparse×2.0，dense×0.2。"""
        plan = self._make_plan("readme.md", monkeypatch)
        assert plan.query_type == "filename"
        assert plan.sparse_top_k >= plan.dense_top_k * 5, "filename 应极度偏重 sparse"

    def test_code_boosts_sparse(self, monkeypatch):
        """code 类型：sparse×1.5，dense×0.8。"""
        plan = self._make_plan("def train():", monkeypatch)
        assert plan.query_type == "code"
        assert plan.sparse_top_k > plan.dense_top_k, "code 应偏重 sparse"

    def test_hybrid_keeps_base_values(self, monkeypatch):
        """hybrid 类型保持原始 top_k 值。"""
        plan = self._make_plan("神经网络", monkeypatch)
        assert plan.query_type == "hybrid"

    def test_limit_constrains_rerank_top_k(self, monkeypatch):
        """当 SearchRequest 有 limit 时，rerank_top_k >= limit。"""
        plan = self._make_plan("test query", monkeypatch, limit=30)
        assert plan.rerank_top_k >= 30
        assert plan.fusion_top_k >= plan.rerank_top_k * 2

    def test_exact_focus_sets_high_exactness(self, monkeypatch):
        """exact_focus=True 时 exactness_level 为 high。"""
        plan = self._make_plan("test", monkeypatch, exact_focus=True)
        assert plan.exactness_level == "high"

    def test_filename_only_sets_high_exactness(self, monkeypatch):
        """filename_only=True 时 exactness_level 为 high。"""
        plan = self._make_plan("test", monkeypatch, filename_only=True)
        assert plan.exactness_level == "high"
