"""Sparse bulk 写入测试。"""

from __future__ import annotations

from types import SimpleNamespace

from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.indexing.sparse_index_writer import SQLiteSparseIndexWriter


def _settings(tmp_path):
    return SimpleNamespace(
        sparse_index_path=str(tmp_path / "sparse.db"),
        sparse_bulk_pragma_fast=False,
    )


def _chunk(chunk_id: str, text: str) -> IndexedChunk:
    return IndexedChunk(
        chunk_id=chunk_id,
        file_id="f1",
        filepath="/tmp/a.md",
        filename="a.md",
        source_type="file",
        filetype="md",
        chunk_type="content",
        title_path=(),
        content=text,
        embedding_text=text,
        sparse_text=text,
        chunk_index=0,
        mtime=1.0,
        ctime=1.0,
        metadata={},
    )


def test_prepare_and_bulk_write(tmp_path):
    writer = SQLiteSparseIndexWriter(_settings(tmp_path))
    prepared = writer.prepare_batch([_chunk("c1", "测试稀疏写入")])
    with writer.open_bulk_session(skip_fts_delete=True) as session:
        session.write_prepared(prepared)

    import sqlite3

    conn = sqlite3.connect(str(tmp_path / "sparse.db"))
    count = conn.execute("SELECT COUNT(*) FROM sparse_chunks").fetchone()[0]
    conn.close()
    assert count == 1


def test_merge_prepared_records():
    from everythingsearch.indexing.sparse_index_writer import PreparedSparseRecords

    left = PreparedSparseRecords((("a",),), (("b",),), ("id1",))
    right = PreparedSparseRecords((("c",),), (("d",),), ("id2",))
    merged = PreparedSparseRecords.merge([left, right])
    assert len(merged.chunk_records) == 2
    assert merged.chunk_ids == ("id1", "id2")
