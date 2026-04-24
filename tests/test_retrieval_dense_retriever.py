"""稠密检索模块单元测试。"""

import tempfile
import pytest

from langchain_core.documents import Document

from everythingsearch.infra.settings import Settings
from everythingsearch.indexing.dense_index_writer import ChromaDenseIndexWriter
from everythingsearch.retrieval.dense_retriever import ChromaDenseRetriever
from everythingsearch.retrieval.models import QueryPlan
from everythingsearch.indexing.chunk_models import IndexedChunk

class DummyEmbedding:
    def embed_documents(self, texts):
        # 简单返回 0.1, 或者根据文本不同返回不同的向量以便测试
        # 测试用例里我们只要它不崩溃就行
        return [[0.1] * 10 for _ in texts]
        
    def embed_query(self, text):
        return [0.1] * 10

@pytest.fixture
def temp_chroma_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d

@pytest.fixture
def mock_settings(temp_chroma_dir):
    class MockSettings:
        persist_directory = temp_chroma_dir
    return MockSettings()

@pytest.fixture
def populated_db(mock_settings):
    embedding = DummyEmbedding()
    writer = ChromaDenseIndexWriter(mock_settings, embedding)
    chunks = [
        IndexedChunk(
            chunk_id="c1",
            file_id="f1",
            filepath="/docs/test.md",
            filename="test.md",
            source_type="file",
            filetype=".md",
            chunk_type="content",
            title_path=(),
            content="test content 1",
            embedding_text="test content 1",
            sparse_text="",
            chunk_index=0,
            mtime=1.0,
            ctime=1.0,
            metadata={"source_type": "file"}
        )
    ]
    writer.upsert_chunks(chunks)
    return mock_settings, embedding

def test_dense_retriever_basic(populated_db):
    settings, embedding = populated_db
    retriever = ChromaDenseRetriever(settings, embedding)
    
    plan = QueryPlan(
        raw_query="test",
        normalized_query="test",
        sparse_query="test",
        dense_query="test",
        query_type="semantic",
        exactness_level="medium",
        source_filter=None,
        date_field="mtime",
        date_from=None,
        date_to=None,
        sparse_top_k=10,
        dense_top_k=10,
        fusion_top_k=10,
        rerank_top_k=10
    )
    
    # 猴子补丁 similarity_search_with_score 以避免实际的向量运算距离都一样
    original_search = retriever._db.similarity_search_with_score
    def mock_search(*args, **kwargs):
        # 假设 distance 是 0.3
        doc = Document(page_content="test content 1", metadata={"chunk_id": "c1", "file_id": "f1"})
        return [(doc, 0.3)]
    
    retriever._db.similarity_search_with_score = mock_search
    
    results = retriever.retrieve(plan)
    assert len(results) == 1
    assert results[0].chunk_id == "c1"
    assert results[0].dense_score == pytest.approx(0.7) # 1.0 - 0.3
