"""结果聚合模块单元测试。"""

import time

import pytest

from everythingsearch.retrieval.aggregation import DefaultFileAggregator
from everythingsearch.retrieval.models import SearchCandidate


def create_candidate(
    cid: str,
    fid: str,
    score: float,
    content: str,
    *,
    chunk_type: str = "content",
    metadata: dict | None = None,
) -> SearchCandidate:
    base_meta = {"author": "AI"}
    if metadata:
        base_meta.update(metadata)
    return SearchCandidate(
        chunk_id=cid,
        file_id=fid,
        filepath=f"/test/{fid}.txt",
        filename=f"{fid}.txt",
        chunk_type=chunk_type,
        content=content,
        title_path=(),
        source_type="file",
        filetype=".txt",
        sparse_rank=None,
        dense_rank=None,
        sparse_score=None,
        dense_score=None,
        fusion_score=score,
        rerank_score=score,  # 为了测试，假设 rerank 成功
        rerank_rank=None,
        metadata=base_meta,
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
    assert abs(results[0].score - 0.815) < 1e-5
    assert results[1].file_id == "f2"
    assert abs(results[1].score - 0.56) < 1e-5
    
    # 检查 highlights
    # f1 有三个不同内容的 chunk, 但 max_highlights=2，且 c4 内容重复
    # f1 content 1, f1 content 2 应该被选中
    f1_highlights = results[0].highlights
    assert len(f1_highlights) == 2
    assert "f1 content 1" in f1_highlights
    assert "f1 content 2" in f1_highlights
    
    # 检查 metadata 传递
    assert results[0].metadata["author"] == "AI"


def test_exact_phrase_bonus():
    """传入 query 时，包含检索词的文档应获得 agg_exact_bonus 加权。"""
    aggregator = DefaultFileAggregator()

    # f1 的 chunk 包含检索词，f2 的不包含
    candidates = [
        create_candidate("c1", "f1", 0.8, "这份文件记录了磨刀石协议的相关内容"),
        create_candidate("c2", "f2", 0.8, "不相关的文件内容"),
    ]

    results_with_query = aggregator.aggregate(candidates, query="磨刀石协议", max_highlights=2)
    results_without_query = aggregator.aggregate(candidates, max_highlights=2)

    # 含检索词的 f1 应该排在 f2 前面（加权后分数更高）
    assert results_with_query[0].file_id == "f1"
    assert results_with_query[1].file_id == "f2"
    # 带 query 时 f1 分数应比不带 query 时高
    assert results_with_query[0].score > results_without_query[0].score


def test_exact_phrase_bonus_short_query_skipped():
    """单字符查询不触发 exact_phrase_bonus，避免常见子串误触发。"""
    aggregator = DefaultFileAggregator()

    candidates = [
        create_candidate("c1", "f1", 0.8, "a"),
        create_candidate("c2", "f2", 0.8, "b"),
    ]

    results_with_query = aggregator.aggregate(candidates, query="a", max_highlights=2)
    results_without_query = aggregator.aggregate(candidates, max_highlights=2)

    # 单字符查询不触发 bonus，分数应与不传 query 时一致
    assert results_with_query[0].score == results_without_query[0].score


def test_recency_bonus_newer_file_ranks_higher():
    """mtime 更新的文件应获得时间加权，在相关性相同时排名更靠前。"""
    aggregator = DefaultFileAggregator()
    now = time.time()
    today_mtime = now - 3600         # 1 小时前
    old_mtime = now - 30 * 86400     # 30 天前

    candidates = [
        create_candidate("c1", "old", 0.8, "old file content", metadata={"mtime": old_mtime}),
        create_candidate("c2", "new", 0.8, "new file content", metadata={"mtime": today_mtime}),
    ]

    results = aggregator.aggregate(candidates, max_highlights=2)

    assert len(results) == 2
    # 新文件应排前面
    assert results[0].file_id == "new"
    assert results[1].file_id == "old"
    # 新文件分数应严格高于旧文件
    assert results[0].score > results[1].score


def test_recency_bonus_old_files_same():
    """mtime 相同的旧文件分数应一致。"""
    aggregator = DefaultFileAggregator()
    now = time.time()
    one_year_ago = now - 365 * 86400

    candidates = [
        create_candidate("c1", "f1", 0.8, "content 1", metadata={"mtime": one_year_ago}),
        create_candidate("c2", "f2", 0.8, "content 2", metadata={"mtime": one_year_ago}),
    ]

    results = aggregator.aggregate(candidates, max_highlights=2)
    assert len(results) == 2
    # 两年老文件的时间加权都接近 0，分数应该相等
    assert abs(results[0].score - results[1].score) < 0.001


def test_recency_bonus_no_mtime_no_crash():
    """mtime 缺失时不抛异常，正常聚合。"""
    aggregator = DefaultFileAggregator()
    candidates = [
        create_candidate("c1", "f1", 0.8, "content 1"),  # 无 mtime
        create_candidate("c2", "f2", 0.8, "content 2", metadata={"mtime": time.time()}),
    ]
    results = aggregator.aggregate(candidates, max_highlights=2)
    assert len(results) == 2
