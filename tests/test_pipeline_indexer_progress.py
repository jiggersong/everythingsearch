"""全量 Pipeline 索引进度接入测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from everythingsearch.indexing import pipeline_indexer
from everythingsearch.indexing.progress_estimator import IndexScaleSnapshot


def test_pipeline_indexer_does_not_import_incremental_module():
    """全量链路不应反向依赖 incremental.py 的私有扫描函数。"""
    source = Path(pipeline_indexer.__file__).read_text(encoding="utf-8")

    assert "everythingsearch.incremental" not in source


def test_calculate_dense_batch_size_caps_large_config():
    """Dense 写入外层批次应避免一次阻塞过多 chunk。"""
    assert pipeline_indexer._calculate_dense_batch_size(5000) == 50
    assert pipeline_indexer._calculate_dense_batch_size(10) == 10
    assert pipeline_indexer._calculate_dense_batch_size(0) == 1


def test_build_pipeline_index_reuses_initial_scale_snapshot(monkeypatch, tmp_path):
    """外部传入规模快照时，全量入口不应重复执行轻量盘点。"""
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
    called = {"disk": 0, "mweb": 0}

    monkeypatch.setattr(pipeline_indexer, "get_settings", lambda: settings)
    monkeypatch.setattr(pipeline_indexer, "require_target_dirs", lambda _settings: (str(tmp_path),))
    monkeypatch.setattr(pipeline_indexer, "require_dashscope_api_key", lambda _settings: "fake-key")
    monkeypatch.setattr(pipeline_indexer, "apply_sdk_environment", lambda _settings: None)
    monkeypatch.setattr(pipeline_indexer, "load_historical_chunks_per_file", lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline_indexer, "scan_files", lambda progress_reporter=None: ([], 0.0))
    monkeypatch.setattr(pipeline_indexer, "scan_mweb_notes", lambda progress_reporter=None: ([], 0.0))

    def fake_disk_scan():
        called["disk"] += 1
        return {}

    def fake_mweb_scan():
        called["mweb"] += 1
        return {}

    monkeypatch.setattr(pipeline_indexer, "scan_disk_files_for_index", fake_disk_scan)
    monkeypatch.setattr(pipeline_indexer, "scan_mweb_notes_for_index", fake_mweb_scan)

    pipeline_indexer.build_pipeline_index(
        initial_scale_snapshot=IndexScaleSnapshot(
            disk_file_count=3,
            mweb_note_count=1,
            pending_file_count=4,
        )
    )

    assert called == {"disk": 0, "mweb": 0}
