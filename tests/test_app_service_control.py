"""搜索服务生命周期管理测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from everythingsearch.infra import app_service_control as asc


def test_resolve_launchd_app_service_reads_instance_label(tmp_path, monkeypatch):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / ".launchd_instance").write_text(
        "LABEL_APP=com.example.app.test\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(asc, "get_project_root", lambda: tmp_path)

    service = asc.resolve_launchd_app_service()
    assert service.label == "com.example.app.test"
    assert service.plist_path == Path.home() / "Library/LaunchAgents/com.example.app.test.plist"
    assert service.bootstrap_domain == f"gui/{os.getuid()}"


def test_list_search_service_pids_filters_by_port_and_process_name(monkeypatch):
    monkeypatch.setattr(
        asc,
        "subprocess",
        type(
            "Subprocess",
            (),
            {
                "run": staticmethod(
                    lambda cmd, **kwargs: asc.subprocess.CompletedProcess(
                        cmd,
                        0,
                        "100\n200\n",
                        "",
                    )
                ),
                "CompletedProcess": asc.subprocess.CompletedProcess,
            },
        )(),
    )
    commands = {
        100: "/path/venv/bin/python -m everythingsearch.app",
        200: "/usr/bin/python other_app.py",
    }
    monkeypatch.setattr(asc, "_process_command", lambda pid: commands.get(pid, ""))

    assert asc.list_search_service_pids(8000) == [100]


def test_stop_search_service_terminates_port_listeners(monkeypatch):
    service = asc.LaunchdAppService(
        label="com.test.app",
        plist_path=Path("/tmp/com.test.app.plist"),
        bootstrap_domain="gui/501",
    )
    monkeypatch.setattr(asc, "resolve_launchd_app_service", lambda: service)
    monkeypatch.setattr(asc, "is_launchd_job_loaded", lambda _service: False)
    monkeypatch.setattr(asc, "list_search_service_pids", lambda port: [123])
    terminated: list[int] = []
    monkeypatch.setattr(asc, "_terminate_pids", lambda pids: terminated.extend(pids))
    monkeypatch.setattr(asc, "_wait_port_listeners_gone", lambda port, timeout_sec=15.0: None)

    snapshot = asc.stop_search_service(8000)
    assert snapshot.service_was_running is True
    assert terminated == [123]


def test_restart_search_service_uses_launchd_when_plist_exists(monkeypatch, tmp_path):
    service = asc.LaunchdAppService(
        label="com.test.app",
        plist_path=tmp_path / "com.test.app.plist",
        bootstrap_domain="gui/501",
    )
    service.plist_path.write_text("plist", encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(asc, "resolve_launchd_app_service", lambda: service)
    monkeypatch.setattr(asc, "is_launchd_job_loaded", lambda _service: True)
    monkeypatch.setattr(asc, "list_search_service_pids", lambda port: [321] if port == 8000 else [])
    monkeypatch.setattr(asc, "_terminate_pids", lambda pids: None)
    monkeypatch.setattr(asc, "_wait_port_listeners_gone", lambda *args, **kwargs: None)

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return asc.subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(asc.subprocess, "run", fake_run)

    snapshot = asc.SearchServiceSnapshot(launchd_was_loaded=True, service_was_running=True)
    assert asc.restart_search_service(8000, snapshot) is True
    assert ["launchctl", "kickstart", "-k", service.job_target] in calls


def test_restart_search_service_starts_when_plist_exists_even_if_stopped(monkeypatch, tmp_path):
    service = asc.LaunchdAppService(
        label="com.test.app",
        plist_path=tmp_path / "com.test.app.plist",
        bootstrap_domain="gui/501",
    )
    service.plist_path.write_text("plist", encoding="utf-8")
    calls: list[list[str]] = []

    monkeypatch.setattr(asc, "resolve_launchd_app_service", lambda: service)
    monkeypatch.setattr(asc, "is_launchd_job_loaded", lambda _service: False)
    listen_states = iter([[], [900]])

    def fake_list(port):
        try:
            return next(listen_states)
        except StopIteration:
            return [900]

    monkeypatch.setattr(asc, "list_search_service_pids", fake_list)
    monkeypatch.setattr(asc, "_terminate_pids", lambda pids: None)
    monkeypatch.setattr(asc, "_wait_port_listeners_gone", lambda *args, **kwargs: None)

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return asc.subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(asc.subprocess, "run", fake_run)

    snapshot = asc.SearchServiceSnapshot(launchd_was_loaded=False, service_was_running=False)
    assert asc.restart_search_service(8000, snapshot) is True
    assert ["launchctl", "bootstrap", service.bootstrap_domain, str(service.plist_path)] in calls
    assert ["launchctl", "kickstart", "-k", service.job_target] in calls


def test_restart_search_service_without_plist_prompts_manual_restart(monkeypatch):
    service = asc.LaunchdAppService(
        label="com.test.app",
        plist_path=Path("/tmp/missing.plist"),
        bootstrap_domain="gui/501",
    )
    monkeypatch.setattr(asc, "resolve_launchd_app_service", lambda: service)

    list_calls = {"count": 0}

    def fake_list(port):
        list_calls["count"] += 1
        return [555] if list_calls["count"] == 1 else []

    monkeypatch.setattr(asc, "list_search_service_pids", fake_list)
    monkeypatch.setattr(asc, "_terminate_pids", lambda _pids: None)
    monkeypatch.setattr(asc, "_wait_port_listeners_gone", lambda *args, **kwargs: None)

    snapshot = asc.SearchServiceSnapshot(launchd_was_loaded=False, service_was_running=True)
    assert asc.restart_search_service(8000, snapshot) is False


def test_suspend_search_service_for_rebuild_restarts_on_exit(monkeypatch):
    events: list[str] = []

    def fake_stop(port):
        events.append("stop")
        return asc.SearchServiceSnapshot(launchd_was_loaded=False, service_was_running=True)

    def fake_restart(port, snapshot):
        events.append("restart")
        return True

    monkeypatch.setattr(asc, "stop_search_service", fake_stop)
    monkeypatch.setattr(asc, "restart_search_service", fake_restart)

    with asc.suspend_search_service_for_rebuild(8000):
        events.append("work")

    assert events == ["stop", "work", "restart"]
