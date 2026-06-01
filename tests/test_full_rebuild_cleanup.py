"""全量重建临时文件清理测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from everythingsearch.indexing import pipeline_indexer
from everythingsearch.indexing.chunk_models import IndexedChunk
from everythingsearch.indexing.full_rebuild_environment import cleanup_rebuild_artifacts
from everythingsearch.indexing.rebuild_checkpoint import RebuildCheckpointStore
from everythingsearch.indexing.rebuild_staging import RebuildStagingStore


def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        rebuild_staging_path=str(tmp_path / "rebuild_staging.db"),
        rebuild_checkpoint_path=str(tmp_path / "rebuild_checkpoint.db"),
    )


def _touch_sqlite_sidecars(db_path: Path) -> list[Path]:
    """创建 SQLite WAL 模式常见的 -wal / -shm 附属文件。"""
    sidecars = [
        db_path.with_name(db_path.name + "-wal"),
        db_path.with_name(db_path.name + "-shm"),
    ]
    for path in sidecars:
        path.touch()
    return sidecars


def test_cleanup_rebuild_artifacts_removes_staging_and_checkpoint(tmp_path):
    settings = _settings(tmp_path)
    staging = Path(settings.rebuild_staging_path)
    checkpoint = Path(settings.rebuild_checkpoint_path)

    RebuildStagingStore(str(staging)).save_chunks(
        [
            IndexedChunk(
                chunk_id="c1",
                file_id="f1",
                filepath="/a.md",
                filename="a.md",
                source_type="file",
                filetype="md",
                chunk_type="content",
                title_path=(),
                content="x" * 10_000,
                embedding_text="x",
                sparse_text="x",
                chunk_index=0,
                mtime=1.0,
                ctime=1.0,
                metadata={},
            )
        ]
    )
    RebuildCheckpointStore(str(checkpoint)).save(
        run_id="run1",
        config_fingerprint="fp",
        phase="dense",
        sparse_batch_end=1,
        dense_batch_end=0,
        total_chunks=1,
    )
    assert staging.exists()
    assert checkpoint.exists()
    staging_sidecars = _touch_sqlite_sidecars(staging)
    checkpoint_sidecars = _touch_sqlite_sidecars(checkpoint)
    for path in staging_sidecars + checkpoint_sidecars:
        assert path.exists()

    freed = cleanup_rebuild_artifacts(settings)

    assert freed > 0
    assert not staging.exists()
    assert not checkpoint.exists()
    for path in staging_sidecars + checkpoint_sidecars:
        assert not path.exists(), f"sidecar 应被删除: {path}"


def test_cleanup_rebuild_artifacts_noop_when_missing(tmp_path):
    settings = _settings(tmp_path)
    assert cleanup_rebuild_artifacts(settings) == 0


def test_build_pipeline_index_removes_artifacts_on_success(monkeypatch, tmp_path):
    settings = SimpleNamespace(
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
    chunk = IndexedChunk(
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

    monkeypatch.setattr(pipeline_indexer, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline_indexer, "require_target_dirs", lambda _s: (str(tmp_path),))
    monkeypatch.setattr(pipeline_indexer, "require_dashscope_api_key", lambda _s: "fake-key")
    monkeypatch.setattr(pipeline_indexer, "apply_sdk_environment", lambda _s: None)
    monkeypatch.setattr(pipeline_indexer, "load_historical_chunks_per_file", lambda *a, **k: None)
    monkeypatch.setattr(pipeline_indexer, "_scan_and_convert_chunks", lambda *a, **k: [chunk])
    monkeypatch.setattr(pipeline_indexer, "reset_dense_collection", lambda _p: None)

    class FakeSparseWriter:
        def open_bulk_session(self, skip_fts_delete=False):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def write_prepared(self, _prepared):
            pass

        def prepare_batch(self, batch):
            return batch

        def optimize(self):
            pass

    monkeypatch.setattr(pipeline_indexer, "SQLiteSparseIndexWriter", lambda _s: FakeSparseWriter())
    monkeypatch.setattr(
        pipeline_indexer,
        "DashScopeEmbeddingProvider",
        lambda _s: SimpleNamespace(
            stats_snapshot=lambda: SimpleNamespace(
                cache_hit_text_count=0,
                uncached_text_count=0,
                remote_batch_count=0,
            )
        ),
    )
    monkeypatch.setattr(
        pipeline_indexer,
        "ChromaDenseIndexWriter",
        lambda _s, _e: SimpleNamespace(upsert_chunks=lambda _c: None),
    )

    ok = pipeline_indexer.build_pipeline_index()

    assert ok is True
    assert not Path(settings.rebuild_staging_path).exists()
    assert not Path(settings.rebuild_checkpoint_path).exists()
