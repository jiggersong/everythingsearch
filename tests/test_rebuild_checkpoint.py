"""重建断点与 staging 测试。"""

from __future__ import annotations

from types import SimpleNamespace

from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.indexing.rebuild_checkpoint import (
    PHASE_DENSE,
    PHASE_SPARSE,
    RebuildCheckpointStore,
    compute_rebuild_config_fingerprint,
)
from everythingsearch.indexing.rebuild_staging import RebuildStagingStore


def _sample_chunk(chunk_id: str = "abc_c0") -> IndexedChunk:
    return IndexedChunk(
        chunk_id=chunk_id,
        file_id="abc",
        filepath="/tmp/a.md",
        filename="a.md",
        source_type="file",
        filetype="md",
        chunk_type="content",
        title_path=("H",),
        content="hello",
        embedding_text="hello",
        sparse_text="hello",
        chunk_index=0,
        mtime=1.0,
        ctime=1.0,
        metadata={},
    )


def test_staging_roundtrip(tmp_path):
    store = RebuildStagingStore(str(tmp_path / "staging.db"))
    chunks = [_sample_chunk("a_c0"), _sample_chunk("a_c1")]
    store.save_chunks(chunks)
    loaded = store.load_chunks()
    assert len(loaded) == 2
    assert {c.chunk_id for c in loaded} == {"a_c0", "a_c1"}


def test_staging_preserves_write_order_not_chunk_id_sort(tmp_path):
    """续跑偏移必须对应写入顺序，而非 chunk_id 字典序。"""
    store = RebuildStagingStore(str(tmp_path / "staging.db"))
    # z 的 chunk_id 字典序在后，但写入顺序在前
    chunks = [_sample_chunk("z_c0"), _sample_chunk("a_c1")]
    store.save_chunks(chunks)
    loaded = store.load_chunks()
    assert [c.chunk_id for c in loaded] == ["z_c0", "a_c1"]


def test_checkpoint_resumable_when_fingerprint_matches(tmp_path):
    settings = SimpleNamespace(
        embedding_model="text-embedding-v4",
        embedding_dimensions=1024,
        embedding_document_text_type="document",
        embedding_query_text_type="query",
        embed_vector_storage_format="blob_float32",
        persist_directory=str(tmp_path / "chroma"),
        sparse_index_path=str(tmp_path / "sparse.db"),
        embedding_cache_path=str(tmp_path / "embed.db"),
    )
    fp = compute_rebuild_config_fingerprint(settings)
    store = RebuildCheckpointStore(str(tmp_path / "checkpoint.db"))
    store.save(
        run_id="run1",
        config_fingerprint=fp,
        phase=PHASE_DENSE,
        sparse_batch_end=10,
        dense_batch_end=3,
        total_chunks=10,
    )
    resume = store.is_resumable(settings)
    assert resume is not None
    assert resume.phase == PHASE_DENSE
    assert resume.dense_batch_end == 3

    settings.embedding_dimensions = 512
    assert store.is_resumable(settings) is None
