"""重排模块单元测试。"""

import pytest
import dashscope
from unittest.mock import patch, MagicMock

from everythingsearch.infra.settings import Settings
from everythingsearch.retrieval.reranking import DashScopeReranker
from everythingsearch.retrieval.models import QueryPlan, SearchCandidate

class MockSettings:
    rerank_model = "qwen3-rerank"
    rerank_top_n = 5
    rerank_max_doc_chars = 2000
    dashscope_api_key = "mock-key"
    
@pytest.fixture
def mock_settings():
    return MockSettings()

def create_candidate(cid: str, content: str, file_id: str | None = None) -> SearchCandidate:
    return SearchCandidate(
        chunk_id=cid,
        file_id=file_id or f"f_{cid}",
        filepath=f"/test/{cid}",
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
        metadata={"mtime": 123.0}
    )

def make_plan(normalized_query: str = "test query") -> QueryPlan:
    return QueryPlan(
        raw_query="test",
        normalized_query=normalized_query,
        sparse_query="",
        dense_query="",
        query_type="semantic",
        exactness_level="medium",
        source_filter=None,
        date_field="mtime",
        date_from=None,
        date_to=None,
        sparse_top_k=10,
        dense_top_k=10,
        fusion_top_k=10,
        rerank_top_k=10,
    )

def test_dashscope_reranker_success(mock_settings):
    reranker = DashScopeReranker(mock_settings)
    plan = QueryPlan(
        raw_query="test", normalized_query="test query", sparse_query="", dense_query="",
        query_type="semantic", exactness_level="medium", source_filter=None,
        date_field="mtime", date_from=None, date_to=None,
        sparse_top_k=10, dense_top_k=10, fusion_top_k=10, rerank_top_k=10
    )
    
    candidates = [
        create_candidate("c1", "bad content"),
        create_candidate("c2", "excellent content")
    ]
    
    with patch("dashscope.TextReRank.call") as mock_call:
        # 模拟 API 返回：c2 分数更高
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # return results: list of items with .document.index and .relevance_score
        item1 = MagicMock()
        del item1.index
        item1.document.index = 1 # c2
        item1.relevance_score = 0.9
        
        item2 = MagicMock()
        del item2.index
        item2.document.index = 0 # c1
        item2.relevance_score = 0.1
        
        mock_resp.output.results = [item1, item2]
        mock_call.return_value = mock_resp
        
        results = reranker.rerank(plan, candidates)
        
        assert len(results) == 2
        # c2 应该在第一位
        assert results[0].chunk_id == "c2"
        assert results[0].rerank_score == 0.9
        assert results[0].rerank_rank == 1
        
        assert results[1].chunk_id == "c1"
        assert results[1].rerank_score == 0.1
        assert results[1].rerank_rank == 2

def test_dashscope_reranker_fallback(mock_settings):
    reranker = DashScopeReranker(mock_settings)
    plan = QueryPlan(
        raw_query="test", normalized_query="test query", sparse_query="", dense_query="",
        query_type="semantic", exactness_level="medium", source_filter=None,
        date_field="mtime", date_from=None, date_to=None,
        sparse_top_k=10, dense_top_k=10, fusion_top_k=10, rerank_top_k=10
    )
    
    candidates = [
        create_candidate("c1", "bad content"),
        create_candidate("c2", "excellent content")
    ]
    
    with patch("dashscope.TextReRank.call") as mock_call:
        # 模拟 API 异常
        mock_call.side_effect = Exception("API Timeout")
        
        results = reranker.rerank(plan, candidates)
        
        # 验证 Fallback 到原顺序
        assert len(results) == 2
        assert results[0].chunk_id == "c1"
        assert results[1].chunk_id == "c2"
        # 分数应为空
        assert results[0].rerank_score is None


def test_dedup_keeps_diff_content_same_prefix(mock_settings):
    """同文件、content 前 50 字相同但全文不同 -> 两个候选都应保留（不被误合并）。"""
    reranker = DashScopeReranker(mock_settings)
    plan = make_plan()
    # 前 50 字符完全相同，但全文不同
    c1 = create_candidate("c1", "A" * 50 + " unique part ONE", file_id="F")
    c2 = create_candidate("c2", "A" * 50 + " unique part TWO", file_id="F")

    with patch("dashscope.TextReRank.call") as mock_call:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        item1 = MagicMock()
        del item1.index
        item1.document.index = 0
        item1.relevance_score = 0.5
        item2 = MagicMock()
        del item2.index
        item2.document.index = 1
        item2.relevance_score = 0.5
        mock_resp.output.results = [item1, item2]
        mock_call.return_value = mock_resp

        results = reranker.rerank(plan, [c1, c2])

        assert len(results) == 2
        assert {r.chunk_id for r in results} == {"c1", "c2"}


def test_dedup_merges_identical_content_diff_chunk(mock_settings):
    """同文件、不同 chunk_id 但物理内容完全相同 -> 仅保留一个（BUG-012 跨 chunk 去重）。"""
    reranker = DashScopeReranker(mock_settings)
    plan = make_plan()
    c1 = create_candidate("c1", "identical body content", file_id="F")
    c2 = create_candidate("c2", "identical body content", file_id="F")

    with patch("dashscope.TextReRank.call") as mock_call:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        item1 = MagicMock()
        del item1.index
        item1.document.index = 0
        item1.relevance_score = 0.9
        mock_resp.output.results = [item1]
        mock_call.return_value = mock_resp

        results = reranker.rerank(plan, [c1, c2])

        assert len(results) == 1
        assert results[0].chunk_id == "c1"
