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


def test_build_pipeline_index_reuses_initial_scale_snapshot(monkeypatch, tmp_path):
    """外部传入规模快照时，全量入口不应重复执行轻量盘点。"""
    settings = SimpleNamespace(
        sparse_index_path=str(tmp_path / "sparse.db"),
        indexer_batch_size=10,
        persist_directory=str(tmp_path / "chroma"),
        embedding_model="text-embedding-v2",
        embedding_cache_path=str(tmp_path / "embedding.db"),
        dashscope_api_key="fake-key",
        embedding_text_type_enabled=False,
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
