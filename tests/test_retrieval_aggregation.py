"""结果聚合模块单元测试。"""

import pytest

from everythingsearch.retrieval.aggregation import DefaultFileAggregator
from everythingsearch.retrieval.models import SearchCandidate

def create_candidate(cid: str, fid: str, score: float, content: str) -> SearchCandidate:
    return SearchCandidate(
        chunk_id=cid,
        file_id=fid,
        filepath=f"/test/{fid}.txt",
        filename=f"{fid}.txt",
        chunk_type="content",
        content=content,
        title_path=(),
        source_type="file",
        filetype=".txt",
        sparse_rank=None,
        dense_rank=None,
        sparse_score=None,
        dense_score=None,
        fusion_score=score,
        rerank_score=score, # 为了测试，假设 rerank 成功
        rerank_rank=None,
        metadata={"author": "AI"}
    )

def test_file_aggregator_basic():
    aggregator = DefaultFileAggregator()
    
    # 模拟传入已经是按分数从高到低排好序的候选集
    candidates = [
        create_candidate("c1", "f1", 0.9, "f1 content 1"),
        create_candidate("c2", "f2", 0.8, "f2 content 1"),
        create_candidate("c3", "f1", 0.7, "f1 content 2"),
        create_candidate("c4", "f1", 0.6, "f1 content 1"), # 重复内容
        create_candidate("c5", "f1", 0.5, "f1 content 3")
    ]
    
    results = aggregator.aggregate(candidates, max_highlights=2)
    
    # 应该聚合出 2 个文件
    assert len(results) == 2
    
    # 排序应该保持 f1(0.9) > f2(0.8)
    assert results[0].file_id == "f1"
    assert results[0].score == 0.9
    assert results[1].file_id == "f2"
    assert results[1].score == 0.8
    
    # 检查 highlights
    # f1 有三个不同内容的 chunk, 但 max_highlights=2，且 c4 内容重复
    # f1 content 1, f1 content 2 应该被选中
    f1_highlights = results[0].highlights
    assert len(f1_highlights) == 2
    assert "f1 content 1" in f1_highlights
    assert "f1 content 2" in f1_highlights
    
    # 检查 metadata 传递
    assert results[0].metadata["author"] == "AI"
