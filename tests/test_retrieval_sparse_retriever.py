"""稀疏检索模块单元测试。"""

import tempfile
import pytest

from everythingsearch.infra.settings import Settings
from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.indexing.sparse_index_writer import SQLiteSparseIndexWriter
from everythingsearch.retrieval.models import QueryPlan
from everythingsearch.retrieval.sparse_retriever import SQLiteSparseRetriever
from everythingsearch.retrieval.query_planner import DefaultQueryPlanner
from everythingsearch.request_validation import SearchRequest

@pytest.fixture
def temp_db_path():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        yield f.name

@pytest.fixture
def mock_settings(temp_db_path):
    class MockSettings:
        sparse_index_path = temp_db_path
        sparse_filename_weight = 8.0
        sparse_path_weight = 3.0
        sparse_heading_weight = 4.0
        sparse_content_weight = 1.0
    return MockSettings()

@pytest.fixture
def populated_db(mock_settings):
    writer = SQLiteSparseIndexWriter(mock_settings)
    chunks = [
        IndexedChunk(
            chunk_id="c1",
            file_id="f1",
            filepath="/docs/architecture.md",
            filename="architecture.md",
            source_type="file",
            filetype=".md",
            chunk_type="content",
            title_path=("System Overview",),
            content="This document describes the neural network architecture.",
            embedding_text="...",
            sparse_text="This document describes the neural network architecture.",
            chunk_index=0,
            mtime=1.0,
            ctime=1.0,
            metadata={}
        ),
        IndexedChunk(
            chunk_id="c2",
            file_id="f2",
            filepath="/docs/neural_network.py",
            filename="neural_network.py",
            source_type="file",
            filetype=".py",
            chunk_type="code",
            title_path=(),
            content="class NeuralNetwork: pass",
            embedding_text="...",
            sparse_text="class NeuralNetwork: pass",
            chunk_index=0,
            mtime=2.0,
            ctime=2.0,
            metadata={}
        )
    ]
    writer.upsert_chunks(chunks)
    return mock_settings

def test_sparse_retriever_basic_search(populated_db):
    retriever = SQLiteSparseRetriever(populated_db)
    planner = DefaultQueryPlanner()
    
    # 搜索 "neural network"
    req = SearchRequest(query="neural network", source="all", date_field="mtime", date_from=None, date_to=None, limit=10)
    plan = planner.plan(req)
    
    results = retriever.retrieve(plan)
    assert len(results) == 2
    
    # c2 命中 filename, 权重更高，分数更好
    # FTS bm25 负数，越小（负越多）越好。我们这里转换了成越大越好。
    # 比较 c1 和 c2 的分数。
    c1_score = next(r.sparse_score for r in results if r.chunk_id == "c1")
    c2_score = next(r.sparse_score for r in results if r.chunk_id == "c2")
    
    # neural_network 命中 filename, weight 8.0, 应该分数大于仅仅命中内容的 c1
    assert c2_score > c1_score

def test_sparse_retriever_source_filter(populated_db):
    retriever = SQLiteSparseRetriever(populated_db)
    planner = DefaultQueryPlanner()
    
    req = SearchRequest(query="neural", source="nonexistent", date_field="mtime", date_from=None, date_to=None, limit=10)
    plan = planner.plan(req)
    
    results = retriever.retrieve(plan)
    assert len(results) == 0

def test_sparse_retriever_time_filter(populated_db):
    retriever = SQLiteSparseRetriever(populated_db)
    planner = DefaultQueryPlanner()
    
    req = SearchRequest(query="neural", source="all", date_field="mtime", date_from=1.5, date_to=None, limit=10)
    plan = planner.plan(req)
    
    results = retriever.retrieve(plan)
    assert len(results) == 1
    assert results[0].chunk_id == "c2"
