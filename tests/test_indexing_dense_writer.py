"""稠密索引写入模块单元测试。"""

import tempfile
import pytest

from everythingsearch.infra.settings import Settings
from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.indexing.dense_index_writer import ChromaDenseIndexWriter

class DummyEmbedding:
    def embed_documents(self, texts):
        # 简单返回假向量
        return [[0.1] * 1536 for _ in texts]
        
    def embed_query(self, text):
        return [0.1] * 1536

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
def sample_chunks():
    return [
        IndexedChunk(
            chunk_id="c1",
            file_id="f1",
            filepath="/tmp/test1.md",
            filename="test1.md",
            source_type="file",
            filetype=".md",
            chunk_type="content",
            title_path=("Header",),
            content="Real content",
            embedding_text="Embedding content",
            sparse_text="Sparse content",
            chunk_index=0,
            mtime=123.0,
            ctime=123.0,
            metadata={"author": "AI"}
        )
    ]

def test_dense_index_writer_upsert(mock_settings, sample_chunks):
    writer = ChromaDenseIndexWriter(mock_settings, DummyEmbedding())
    writer.upsert_chunks(sample_chunks)
    
    # 验证数据写入 Chroma
    col = writer._client.get_collection("local_files")
    assert col.count() == 1
    
    data = col.get()
    assert "c1" in data["ids"]
    
    idx = data["ids"].index("c1")
    assert data["documents"][idx] == "Embedding content"
    meta = data["metadatas"][idx]
    assert meta["file_id"] == "f1"
    assert meta["author"] == "AI"

def test_dense_index_writer_delete(mock_settings, sample_chunks):
    writer = ChromaDenseIndexWriter(mock_settings, DummyEmbedding())
    writer.upsert_chunks(sample_chunks)
    
    writer.delete_file("f1")
    
    col = writer._client.get_collection("local_files")
    assert col.count() == 0
