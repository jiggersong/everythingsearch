"""增量索引进度接入测试。"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from everythingsearch import incremental
from everythingsearch.indexing.progress_estimator import IndexScaleSnapshot
from everythingsearch.infra.app_service_control import SearchServiceSnapshot


def test_delete_chunks_raises_when_both_dense_deletes_fail():
    """Dense 删除两种 where 都失败时应显式抛错。"""

    class FailingCollection:
        def delete(self, where):
            raise RuntimeError(f"delete failed: {where}")

    try:
        incremental._delete_chunks(FailingCollection(), "/tmp/fail.md")
    except RuntimeError as exc:
        assert "删除 Dense 索引失败" in str(exc)
    else:
        assert False, "expected RuntimeError"


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
        rebuild_staging_path=str(tmp_path / "staging.db"),
        rebuild_checkpoint_path=str(tmp_path / "checkpoint.db"),
        index_run_lock_path=str(tmp_path / "index_run.lock"),
        port=8000,
        enable_mweb=False,
        mweb_export_script=None,
    )
    captured: dict[str, object] = {}
    _patch_incremental_missing_collection(monkeypatch, tmp_path, settings)

    def fake_build_pipeline_index(initial_scale_snapshot=None, transition_reason=None, full_rebuild_plan=None):
        captured["snapshot"] = initial_scale_snapshot
        captured["reason"] = transition_reason
        captured["plan"] = full_rebuild_plan
        return True

    prepare_called = {"value": False}

    def _fake_prepare(settings, plan):
        prepare_called["value"] = True

    monkeypatch.setattr(incremental, "prepare_full_rebuild_environment", _fake_prepare)

    monkeypatch.setattr(
        "everythingsearch.indexing.pipeline_indexer.build_pipeline_index",
        fake_build_pipeline_index,
    )
    monkeypatch.setattr(incremental, "_rebuild_state_db", lambda: captured.setdefault("state_rebuilt", True))

    incremental.run_incremental()

    assert isinstance(captured["snapshot"], IndexScaleSnapshot)
    assert captured["snapshot"].disk_file_count == 1
    assert captured["snapshot"].pending_file_count == 1
    assert captured["reason"] == "Dense collection 不存在"
    assert captured.get("state_rebuilt") is True
    assert captured["plan"] is not None
    assert captured["plan"].keep_embedding_cache is True
    assert prepare_called["value"] is True


def _patch_incremental_missing_collection(monkeypatch, tmp_path, settings):
    monkeypatch.setattr(incremental, "get_settings", lambda: settings)
    monkeypatch.setattr(incremental, "require_target_dirs", lambda _settings: (str(tmp_path),))
    monkeypatch.setattr(incremental, "require_dashscope_api_key", lambda _settings: "fake-key")
    monkeypatch.setattr(incremental, "apply_sdk_environment", lambda _settings: None)
    monkeypatch.setattr(incremental, "scan_disk_files_for_index", lambda: {str(tmp_path / "a.md"): (1.0, "file")})
    monkeypatch.setattr(incremental, "scan_mweb_notes_for_index", lambda: {})
    monkeypatch.setattr(incremental, "load_historical_chunks_per_file", lambda *args, **kwargs: None)

    @contextmanager
    def _noop_suspend(port):
        yield SearchServiceSnapshot(launchd_was_loaded=False, service_was_running=False)

    monkeypatch.setattr(incremental, "suspend_search_service_for_rebuild", _noop_suspend)
    monkeypatch.setattr(incremental, "_reload_app_service_after_indexing", lambda: None)

    class FakeClient:
        def __init__(self, path):
            self.path = path

        def list_collections(self):
            return []

    monkeypatch.setattr(incremental.chromadb, "PersistentClient", FakeClient)


def test_incremental_fallback_exits_when_full_rebuild_fails(monkeypatch, tmp_path):
    """Dense 缺失且全量 fallback 失败时应以非 0 退出，避免定时任务误判成功。"""
    settings = SimpleNamespace(
        index_state_db=str(tmp_path / "state.db"),
        sparse_index_path=str(tmp_path / "sparse.db"),
        persist_directory=str(tmp_path / "chroma"),
        scan_cache_path=str(tmp_path / "scan_cache.db"),
        embedding_model="text-embedding-v2",
        embedding_cache_path=str(tmp_path / "embedding.db"),
        rebuild_staging_path=str(tmp_path / "staging.db"),
        rebuild_checkpoint_path=str(tmp_path / "checkpoint.db"),
        index_run_lock_path=str(tmp_path / "index_run.lock"),
        port=8000,
        enable_mweb=False,
        mweb_export_script=None,
    )
    _patch_incremental_missing_collection(monkeypatch, tmp_path, settings)
    monkeypatch.setattr(
        "everythingsearch.indexing.pipeline_indexer.build_pipeline_index",
        lambda **kwargs: False,
    )
    state_rebuilt = {"called": False}
    monkeypatch.setattr(incremental, "_rebuild_state_db", lambda: state_rebuilt.update(called=True))

    with pytest.raises(SystemExit) as exc_info:
        incremental.run_incremental()

    assert exc_info.value.code == 1
    assert state_rebuilt["called"] is False


def test_incremental_sparse_failure_skips_state_and_rolls_back_dense(monkeypatch, tmp_path):
    """Sparse 写失败时不应标记 file_index，且应回滚 Dense。"""
    import os
    import sqlite3
    from pathlib import Path

    from langchain_core.documents import Document

    fp = str(tmp_path / "a.md")
    Path(fp).write_text("# title\n\nbody", encoding="utf-8")
    mtime = os.path.getmtime(fp)

    state_db = tmp_path / "state.db"
    settings = SimpleNamespace(
        index_state_db=str(state_db),
        sparse_index_path=str(tmp_path / "sparse.db"),
        persist_directory=str(tmp_path / "chroma"),
        scan_cache_path="",
        embedding_model="text-embedding-v2",
        embedding_cache_path=str(tmp_path / "embedding.db"),
        index_run_lock_path=str(tmp_path / "index_run.lock"),
        port=8000,
        enable_mweb=False,
        mweb_export_script=None,
    )

    conn = sqlite3.connect(state_db)
    incremental._init_state_db(conn)
    conn.close()

    class FakeCollection:
        name = "local_files"

        def delete(self, where):
            return None

    class FakeClient:
        def __init__(self, path):
            self.path = path

        def list_collections(self):
            return [FakeCollection()]

        def get_collection(self, name):
            return FakeCollection()

    deleted_file_ids: list[str] = []

    class FakeDenseWriter:
        def upsert_chunks(self, chunks):
            return None

        def delete_file(self, file_id):
            deleted_file_ids.append(file_id)

    class FakeSparseWriter:
        def upsert_chunks(self, chunks):
            raise RuntimeError("sparse boom")

        def delete_file(self, file_id):
            return None

    monkeypatch.setattr(incremental, "get_settings", lambda: settings)
    monkeypatch.setattr(incremental, "require_target_dirs", lambda _s: (str(tmp_path),))
    monkeypatch.setattr(incremental, "require_dashscope_api_key", lambda _s: "fake-key")
    monkeypatch.setattr(incremental, "apply_sdk_environment", lambda _s: None)
    monkeypatch.setattr(incremental, "scan_disk_files_for_index", lambda: {fp: (mtime, "file")})
    monkeypatch.setattr(incremental, "scan_mweb_notes_for_index", lambda: {})
    monkeypatch.setattr(incremental, "load_historical_chunks_per_file", lambda *a, **k: None)
    monkeypatch.setattr(incremental.chromadb, "PersistentClient", FakeClient)
    monkeypatch.setattr(
        incremental,
        "DashScopeEmbeddingProvider",
        lambda _s: SimpleNamespace(
            stats_snapshot=lambda: SimpleNamespace(
                cache_hit_text_count=0,
                uncached_text_count=0,
                remote_batch_count=0,
            )
        ),
    )
    monkeypatch.setattr(incremental, "ChromaDenseIndexWriter", lambda _s, _e: FakeDenseWriter())
    monkeypatch.setattr(incremental, "SQLiteSparseIndexWriter", lambda _s: FakeSparseWriter())
    monkeypatch.setattr(
        incremental,
        "build_documents_for_path_cached",
        lambda *a, **k: [Document(page_content="body", metadata={"source_type": "file"})],
    )
    restart_called = {"value": False}
    monkeypatch.setattr(
        incremental,
        "_reload_app_service_after_indexing",
        lambda: restart_called.update(value=True),
    )

    incremental.run_incremental()

    conn = sqlite3.connect(state_db)
    row = conn.execute("SELECT 1 FROM file_index WHERE filepath = ?", (fp,)).fetchone()
    conn.close()

    assert row is None
    assert len(deleted_file_ids) == 1


def test_incremental_success_restarts_app_service(monkeypatch, tmp_path):
    """增量成功完成后应重启搜索服务。"""
    import os
    import sqlite3
    from pathlib import Path

    fp = str(tmp_path / "a.md")
    Path(fp).write_text("body", encoding="utf-8")
    mtime = os.path.getmtime(fp)
    state_db = tmp_path / "state.db"
    settings = SimpleNamespace(
        index_state_db=str(state_db),
        sparse_index_path=str(tmp_path / "sparse.db"),
        persist_directory=str(tmp_path / "chroma"),
        scan_cache_path="",
        embedding_model="text-embedding-v2",
        embedding_cache_path=str(tmp_path / "embedding.db"),
        index_run_lock_path=str(tmp_path / "index_run.lock"),
        port=8000,
        enable_mweb=False,
        mweb_export_script=None,
    )

    conn = sqlite3.connect(state_db)
    incremental._init_state_db(conn)
    conn.close()

    class FakeCollection:
        name = "local_files"

        def delete(self, where):
            return None

    class FakeClient:
        def __init__(self, path=None):
            self.path = path

        def list_collections(self):
            return [FakeCollection()]

        def get_collection(self, name):
            return FakeCollection()

    class FakeDenseWriter:
        def upsert_chunks(self, chunks):
            return None

        def delete_file(self, file_id):
            return None

    class FakeSparseWriter:
        def upsert_chunks(self, chunks):
            return None

        def delete_file(self, file_id):
            return None

    from langchain_core.documents import Document

    monkeypatch.setattr(incremental, "get_settings", lambda: settings)
    monkeypatch.setattr(incremental, "require_target_dirs", lambda _s: (str(tmp_path),))
    monkeypatch.setattr(incremental, "require_dashscope_api_key", lambda _s: "fake-key")
    monkeypatch.setattr(incremental, "apply_sdk_environment", lambda _s: None)
    monkeypatch.setattr(incremental, "scan_disk_files_for_index", lambda: {fp: (mtime, "file")})
    monkeypatch.setattr(incremental, "scan_mweb_notes_for_index", lambda: {})
    monkeypatch.setattr(incremental, "load_historical_chunks_per_file", lambda *a, **k: None)
    monkeypatch.setattr(incremental.chromadb, "PersistentClient", FakeClient)
    monkeypatch.setattr(
        incremental,
        "DashScopeEmbeddingProvider",
        lambda _s: SimpleNamespace(
            stats_snapshot=lambda: SimpleNamespace(
                cache_hit_text_count=0,
                uncached_text_count=1,
                remote_batch_count=1,
            )
        ),
    )
    monkeypatch.setattr(incremental, "ChromaDenseIndexWriter", lambda _s, _e: FakeDenseWriter())
    monkeypatch.setattr(incremental, "SQLiteSparseIndexWriter", lambda _s: FakeSparseWriter())
    monkeypatch.setattr(
        incremental,
        "build_documents_for_path_cached",
        lambda *a, **k: [Document(page_content="body", metadata={"source_type": "file"})],
    )
    restart_called = {"value": False}
    monkeypatch.setattr(
        incremental,
        "restart_search_service",
        lambda port, snapshot=None: restart_called.update(value=True) or True,
    )

    incremental.run_incremental()
    assert restart_called["value"] is True
