"""稀疏索引写入模块单元测试。"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from everythingsearch.infra.settings import Settings
from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.indexing.sparse_index_writer import SQLiteSparseIndexWriter

@pytest.fixture
def temp_db_path():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        yield f.name

@pytest.fixture
def mock_settings(temp_db_path, monkeypatch):
    # 创建一个能用的设置实例
    # 用到的只有 sparse_index_path
    class MockSettings:
        sparse_index_path = temp_db_path
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
            content="这是一段包含人工智能的中文测试文本。",
            embedding_text="...",
            sparse_text="这是一段包含人工智能的中文测试文本。",
            chunk_index=0,
            mtime=123.0,
            ctime=123.0,
            metadata={"author": "AI"}
        ),
        IndexedChunk(
            chunk_id="c2",
            file_id="f2",
            filepath="/tmp/test2.py",
            filename="test2.py",
            source_type="file",
            filetype=".py",
            chunk_type="code",
            title_path=(),
            content="def hello_world(): print('hello')",
            embedding_text="...",
            sparse_text="def hello_world(): print('hello')",
            chunk_index=0,
            mtime=124.0,
            ctime=124.0,
            metadata={}
        )
    ]

def test_sparse_index_writer_init(mock_settings):
    writer = SQLiteSparseIndexWriter(mock_settings)
    # 验证表被创建
    conn = sqlite3.connect(mock_settings.sparse_index_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sparse_chunks'")
    assert cursor.fetchone() is not None
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sparse_chunks_fts'")
    assert cursor.fetchone() is not None

def test_sparse_index_writer_upsert(mock_settings, sample_chunks):
    writer = SQLiteSparseIndexWriter(mock_settings)
    writer.upsert_chunks(sample_chunks)
    
    conn = sqlite3.connect(mock_settings.sparse_index_path)
    cursor = conn.cursor()
    cursor.execute("SELECT chunk_id FROM sparse_chunks")
    rows = cursor.fetchall()
    assert len(rows) == 2
    
    # 检查 jieba 分词是否写入 FTS
    cursor.execute("SELECT content_text FROM sparse_chunks_fts WHERE chunk_id='c1'")
    fts_content = cursor.fetchone()[0]
    # "人工智能" 应该作为一个词被切分出来
    assert "人工" in fts_content or "智能" in fts_content or "人工智能" in fts_content

def test_sparse_index_writer_delete(mock_settings, sample_chunks):
    writer = SQLiteSparseIndexWriter(mock_settings)
    writer.upsert_chunks(sample_chunks)
    
    writer.delete_file("f1")
    
    conn = sqlite3.connect(mock_settings.sparse_index_path)
    cursor = conn.cursor()
    cursor.execute("SELECT chunk_id FROM sparse_chunks")
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "c2"
    
    cursor.execute("SELECT chunk_id FROM sparse_chunks_fts")
    fts_rows = cursor.fetchall()
    assert len(fts_rows) == 1
    assert fts_rows[0][0] == "c2"
