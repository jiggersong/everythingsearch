"""增量索引进度接入测试。"""

from __future__ import annotations

from types import SimpleNamespace

from everythingsearch import incremental
from everythingsearch.indexing.progress_estimator import IndexScaleSnapshot


def test_incremental_missing_collection_passes_scale_snapshot_to_full_rebuild(monkeypatch, tmp_path):
    """Dense collection 缺失时应把已计算的规模快照传给全量入口。"""
    state_db = tmp_path / "state.db"
    settings = SimpleNamespace(
        index_state_db=str(state_db),
        sparse_index_path=str(tmp_path / "sparse.db"),
        persist_directory=str(tmp_path / "chroma"),
        scan_cache_path=str(tmp_path / "scan_cache.db"),
        embedding_model="text-embedding-v2",
        embedding_cache_path=str(tmp_path / "embedding.db"),
        enable_mweb=False,
        mweb_export_script=None,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(incremental, "get_settings", lambda: settings)
    monkeypatch.setattr(incremental, "require_target_dirs", lambda _settings: (str(tmp_path),))
    monkeypatch.setattr(incremental, "require_dashscope_api_key", lambda _settings: "fake-key")
    monkeypatch.setattr(incremental, "apply_sdk_environment", lambda _settings: None)
    monkeypatch.setattr(incremental, "_scan_disk_files", lambda: {str(tmp_path / "a.md"): (1.0, "file")})
    monkeypatch.setattr(incremental, "_scan_disk_mweb", lambda: {})
    monkeypatch.setattr(incremental, "load_historical_chunks_per_file", lambda *args, **kwargs: None)

    class FakeClient:
        def __init__(self, path):
            self.path = path

        def list_collections(self):
            return []

    def fake_build_pipeline_index(initial_scale_snapshot=None, transition_reason=None):
        captured["snapshot"] = initial_scale_snapshot
        captured["reason"] = transition_reason

    monkeypatch.setattr(incremental.chromadb, "PersistentClient", FakeClient)
    monkeypatch.setattr(
        "everythingsearch.indexing.pipeline_indexer.build_pipeline_index",
        fake_build_pipeline_index,
    )

    incremental.run_incremental()

    assert isinstance(captured["snapshot"], IndexScaleSnapshot)
    assert captured["snapshot"].disk_file_count == 1
    assert captured["snapshot"].pending_file_count == 1
    assert captured["reason"] == "Dense collection 不存在"
