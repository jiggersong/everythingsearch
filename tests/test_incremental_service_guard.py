"""索引入口的服务管理与锁集成测试。"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from everythingsearch import incremental
from everythingsearch.indexing.full_rebuild_plan import FullRebuildPlan
from everythingsearch.infra.app_service_control import SearchServiceSnapshot
from everythingsearch.infra.index_run_lock import IndexRunLock


def test_run_incremental_skips_when_lock_busy(monkeypatch, tmp_path):
    lock_path = str(tmp_path / "index_run.lock")
    settings = SimpleNamespace(index_run_lock_path=lock_path)
    monkeypatch.setattr(incremental, "get_settings", lambda: settings)

    lock = IndexRunLock(lock_path, "full")
    assert lock.try_acquire()

    called = {"value": False}
    monkeypatch.setattr(incremental, "_run_incremental_impl", lambda: called.__setitem__("value", True))

    incremental.run_incremental()
    assert called["value"] is False
    lock.release()


def test_run_full_suspends_and_restarts_search_service(monkeypatch, tmp_path):
    lock_path = str(tmp_path / "index_run.lock")
    settings = SimpleNamespace(
        index_run_lock_path=lock_path,
        port=8000,
        index_state_db=str(tmp_path / "state.db"),
        sparse_index_path=str(tmp_path / "sparse.db"),
        persist_directory=str(tmp_path / "chroma"),
        scan_cache_path=str(tmp_path / "scan.db"),
        embedding_cache_path=str(tmp_path / "embed.db"),
        rebuild_staging_path=str(tmp_path / "staging.db"),
        rebuild_checkpoint_path=str(tmp_path / "checkpoint.db"),
    )
    monkeypatch.setattr(incremental, "get_settings", lambda: settings)
    monkeypatch.setattr(incremental, "require_target_dirs", lambda _s: None)
    monkeypatch.setattr(incremental, "require_dashscope_api_key", lambda _s: None)
    monkeypatch.setattr(incremental, "apply_sdk_environment", lambda _s: None)
    monkeypatch.setattr(incremental, "prepare_full_rebuild_environment", lambda *_a, **_k: None)
    monkeypatch.setattr(incremental, "_rebuild_state_db", lambda: None)
    monkeypatch.setattr(
        "everythingsearch.indexing.pipeline_indexer.build_pipeline_index",
        lambda **kwargs: True,
    )

    events: list[str] = []

    @contextmanager
    def fake_suspend(port):
        events.append(f"suspend:{port}")
        yield SearchServiceSnapshot(launchd_was_loaded=False, service_was_running=True)
        events.append("resumed")

    monkeypatch.setattr(incremental, "suspend_search_service_for_rebuild", fake_suspend)
    monkeypatch.setattr(incremental, "_reload_app_service_after_indexing", lambda: events.append("reload"))

    incremental.run_full(FullRebuildPlan())

    assert events == ["suspend:8000", "resumed", "reload"]


def test_run_full_exits_when_lock_busy(monkeypatch, tmp_path):
    lock_path = str(tmp_path / "index_run.lock")
    settings = SimpleNamespace(index_run_lock_path=lock_path, port=8000)
    monkeypatch.setattr(incremental, "get_settings", lambda: settings)
    monkeypatch.setattr(incremental, "require_target_dirs", lambda _s: None)
    monkeypatch.setattr(incremental, "require_dashscope_api_key", lambda _s: None)
    monkeypatch.setattr(incremental, "apply_sdk_environment", lambda _s: None)

    lock = IndexRunLock(lock_path, "incremental")
    assert lock.try_acquire()

    with pytest.raises(SystemExit) as exc:
        incremental.run_full(FullRebuildPlan())
    assert exc.value.code == 1
    lock.release()


def test_reload_app_service_after_indexing_warns_when_not_started(monkeypatch, caplog):
    import logging

    settings = SimpleNamespace(port=8000)
    monkeypatch.setattr(incremental, "get_settings", lambda: settings)
    monkeypatch.setattr(incremental, "restart_search_service", lambda port, snapshot=None: False)

    with caplog.at_level(logging.WARNING):
        incremental._reload_app_service_after_indexing()

    assert "搜索服务未自动启动" in caplog.text


def test_reload_app_service_after_indexing_exits_on_failure(monkeypatch):
    settings = SimpleNamespace(port=8000)
    monkeypatch.setattr(incremental, "get_settings", lambda: settings)
    monkeypatch.setattr(
        incremental,
        "restart_search_service",
        lambda port, snapshot=None: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(SystemExit) as exc:
        incremental._reload_app_service_after_indexing()
    assert exc.value.code == 1
