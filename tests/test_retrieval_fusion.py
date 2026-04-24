"""融合模块单元测试。"""

import pytest

from everythingsearch.retrieval.fusion import RRFCandidateFusion
from everythingsearch.retrieval.models import QueryPlan, SearchCandidate

class MockSettings:
    rrf_k = 60
    fusion_top_k = 10

def create_candidate(cid: str, rank: int, score: float, is_sparse: bool) -> SearchCandidate:
    return SearchCandidate(
        chunk_id=cid,
        file_id=f"f_{cid}",
        filepath=f"/test/{cid}",
        filename=cid,
        chunk_type="content",
        content="test",
        title_path=(),
        source_type="file",
        filetype=".txt",
        sparse_rank=rank if is_sparse else None,
        dense_rank=None if is_sparse else rank,
        sparse_score=score if is_sparse else None,
        dense_score=None if is_sparse else score,
        fusion_score=0.0,
        metadata={}
    )

def test_rrf_fusion_basic():
    fusion = RRFCandidateFusion(MockSettings())
    plan = QueryPlan(
        raw_query="test", normalized_query="test", sparse_query="test", dense_query="test",
        query_type="hybrid", exactness_level="medium", source_filter=None,
        date_field="mtime", date_from=None, date_to=None,
        sparse_top_k=10, dense_top_k=10, fusion_top_k=10, rerank_top_k=10
    )
    
    # 构造候选
    # sparse 独有 c1
    # dense 独有 c2
    # 共有 c3
    sparse_candidates = [
        create_candidate("c3", 1, 0.9, True),
        create_candidate("c1", 2, 0.8, True)
    ]
    dense_candidates = [
        create_candidate("c2", 1, 0.9, False),
        create_candidate("c3", 2, 0.8, False)
    ]
    
    fused = fusion.fuse(sparse_candidates, dense_candidates, plan)
    
    assert len(fused) == 3
    # c3 应该在第一，因为两路都有召回
    # 对于 hybrid, weights = 1.0, 1.0
    # c3 = 1.0/(60+1) + 1.0/(60+2) = 1/61 + 1/62
    # c1 = 1.0/(60+2) = 1/62
    # c2 = 1.0/(60+1) = 1/61
    
    assert fused[0].chunk_id == "c3"
    assert fused[1].chunk_id == "c2" # c2 (1/61) > c1 (1/62)
    assert fused[2].chunk_id == "c1"

def test_rrf_fusion_weights():
    fusion = RRFCandidateFusion(MockSettings())
    # exact 查询，sparse 权重高 (1.4 vs 0.7)
    plan = QueryPlan(
        raw_query="test", normalized_query="test", sparse_query="test", dense_query="test",
        query_type="exact", exactness_level="medium", source_filter=None,
        date_field="mtime", date_from=None, date_to=None,
        sparse_top_k=10, dense_top_k=10, fusion_top_k=10, rerank_top_k=10
    )
    
    sparse_candidates = [create_candidate("c1", 1, 0.9, True)]
    dense_candidates = [create_candidate("c2", 1, 0.9, False)]
    
    fused = fusion.fuse(sparse_candidates, dense_candidates, plan)
    
    # c1 应该排前面，因为 sparse_weight (1.4) > dense_weight (0.7)
    assert fused[0].chunk_id == "c1"
    assert fused[1].chunk_id == "c2"
