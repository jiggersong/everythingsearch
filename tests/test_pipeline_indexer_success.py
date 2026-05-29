"""全量索引成功/失败返回值测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from everythingsearch.indexing import pipeline_indexer
from everythingsearch.indexing.chunk_models import IndexedChunk


def test_build_pipeline_index_returns_false_when_sparse_write_fails(monkeypatch, tmp_path):
    settings = _pipeline_settings(tmp_path)
    _patch_pipeline_basics(monkeypatch, settings, tmp_path)

    class FakeSparseWriter:
        def upsert_chunks(self, chunks):
            raise RuntimeError("sparse boom")

        def optimize(self):
            pass

    monkeypatch.setattr(pipeline_indexer, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline_indexer, "require_target_dirs", lambda _s: (str(tmp_path),))
    monkeypatch.setattr(pipeline_indexer, "require_dashscope_api_key", lambda _s: "fake-key")
    monkeypatch.setattr(pipeline_indexer, "apply_sdk_environment", lambda _s: None)
    monkeypatch.setattr(pipeline_indexer, "load_historical_chunks_per_file", lambda *a, **k: None)
    monkeypatch.setattr(
        pipeline_indexer,
        "_scan_and_convert_chunks",
        lambda *a, **k: [
            IndexedChunk(
                chunk_id="c1",
                file_id="f1",
                filepath="/a.md",
                filename="a.md",
                source_type="file",
                filetype="md",
                chunk_type="content",
                title_path=(),
                content="x",
                embedding_text="x",
                sparse_text="x",
                chunk_index=0,
                mtime=1.0,
                ctime=1.0,
                metadata={},
            )
        ],
    )
    monkeypatch.setattr(pipeline_indexer, "SQLiteSparseIndexWriter", lambda _s: FakeSparseWriter())
    monkeypatch.setattr(
        pipeline_indexer,
        "DashScopeEmbeddingProvider",
        lambda _s: SimpleNamespace(stats_snapshot=lambda: SimpleNamespace(
            cache_hit_text_count=0, uncached_text_count=0, remote_batch_count=0
        )),
    )
    monkeypatch.setattr(
        pipeline_indexer,
        "ChromaDenseIndexWriter",
        lambda _s, _e: SimpleNamespace(upsert_chunks=lambda _c: None),
    )
    monkeypatch.setattr(pipeline_indexer, "reset_dense_collection", lambda _p: None)

    ok = pipeline_indexer.build_pipeline_index()
    assert ok is False


def _pipeline_settings(tmp_path):
    return SimpleNamespace(
        sparse_index_path=str(tmp_path / "sparse.db"),
        indexer_batch_size=10,
        sparse_index_batch_size=10,
        sparse_checkpoint_interval=10,
        sparse_tokenize_workers=1,
        sparse_bulk_pragma_fast=False,
        sparse_skip_fts_delete_on_fresh=True,
        persist_directory=str(tmp_path / "chroma"),
        embedding_model="text-embedding-v2",
        embedding_cache_path=str(tmp_path / "embedding.db"),
        dashscope_api_key="fake-key",
        embedding_dimensions=None,
        embedding_document_text_type="document",
        embedding_query_text_type="query",
        embed_vector_storage_format="blob_float32",
        embed_rate_rps_limit=20.0,
        embed_rate_tpm_limit=900000.0,
        embed_max_inflight=6,
        embed_retry_max=5,
        embed_backoff_base_ms=500,
        embed_backoff_max_ms=15000,
        rebuild_checkpoint_path=str(tmp_path / "rebuild_checkpoint.db"),
        rebuild_staging_path=str(tmp_path / "rebuild_staging.db"),
    )


def _patch_pipeline_basics(monkeypatch, settings, tmp_path):
    monkeypatch.setattr(pipeline_indexer, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline_indexer, "require_target_dirs", lambda _s: (str(tmp_path),))
    monkeypatch.setattr(pipeline_indexer, "require_dashscope_api_key", lambda _s: "fake-key")
    monkeypatch.setattr(pipeline_indexer, "apply_sdk_environment", lambda _s: None)
    monkeypatch.setattr(pipeline_indexer, "load_historical_chunks_per_file", lambda *a, **k: None)


def test_build_pipeline_index_succeeds_when_scan_is_empty(monkeypatch, tmp_path):
    settings = _pipeline_settings(tmp_path)
    _patch_pipeline_basics(monkeypatch, settings, tmp_path)
    monkeypatch.setattr(pipeline_indexer, "_scan_and_convert_chunks", lambda *a, **k: [])
    reset_called = {"value": False}
    monkeypatch.setattr(
        pipeline_indexer,
        "reset_dense_collection",
        lambda _p: reset_called.update(value=True),
    )

    ok = pipeline_indexer.build_pipeline_index()

    assert ok is True
    assert reset_called["value"] is True
    assert Path(settings.sparse_index_path).exists()


def test_build_pipeline_index_resume_fails_when_staging_empty(monkeypatch, tmp_path):
    from everythingsearch.indexing.full_rebuild_plan import FullRebuildPlan
    from everythingsearch.indexing.rebuild_checkpoint import PHASE_SPARSE, RebuildCheckpoint

    settings = _pipeline_settings(tmp_path)
    _patch_pipeline_basics(monkeypatch, settings, tmp_path)
    plan = FullRebuildPlan(resume=True)
    resume = RebuildCheckpoint(
        run_id="run1",
        config_fingerprint=pipeline_indexer.compute_rebuild_config_fingerprint(settings),
        phase=PHASE_SPARSE,
        sparse_batch_end=0,
        dense_batch_end=0,
        total_chunks=10,
        updated_at=1.0,
    )
    monkeypatch.setattr(
        pipeline_indexer.RebuildCheckpointStore,
        "is_resumable",
        lambda self, _s: resume,
    )
    monkeypatch.setattr(
        pipeline_indexer.RebuildStagingStore,
        "load_chunks",
        lambda self: [],
    )
    scan_called = {"value": False}
    monkeypatch.setattr(
        pipeline_indexer,
        "_scan_and_convert_chunks",
        lambda *a, **k: scan_called.update(value=True) or [],
    )

    ok = pipeline_indexer.build_pipeline_index(full_rebuild_plan=plan)

    assert ok is False
    assert scan_called["value"] is False
