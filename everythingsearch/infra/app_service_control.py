"""搜索服务生命周期管理（launchd 与手动启动统一处理）。"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .paths import get_project_root

logger = logging.getLogger(__name__)

_DEFAULT_APP_LABEL = "com.jigger.everythingsearch.app"
_PROCESS_MARKERS = ("everythingsearch",)


@dataclass(frozen=True)
class LaunchdAppService:
    """launchd 管理的搜索服务描述。"""

    label: str
    plist_path: Path
    bootstrap_domain: str

    @property
    def job_target(self) -> str:
        return f"{self.bootstrap_domain}/{self.label}"


@dataclass(frozen=True)
class SearchServiceSnapshot:
    """索引前后搜索服务状态快照。"""

    launchd_was_loaded: bool
    service_was_running: bool


def resolve_launchd_app_service(project_root: Path | None = None) -> LaunchdAppService:
    """从项目实例文件解析当前安装对应的 launchd App 服务。"""
    root = project_root or get_project_root()
    label = _DEFAULT_APP_LABEL
    instance_file = root / "scripts" / ".launchd_instance"
    if instance_file.is_file():
        for line in instance_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("LABEL_APP="):
                label = line.split("=", 1)[1].strip()
                break
    domain = f"gui/{os.getuid()}"
    plist_path = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    return LaunchdAppService(label=label, plist_path=plist_path, bootstrap_domain=domain)


def is_launchd_job_loaded(service: LaunchdAppService) -> bool:
    """判断 launchd job 是否已加载。"""
    result = subprocess.run(
        ["launchctl", "print", service.job_target],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def _process_command(pid: int) -> str:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout or "").strip()


def _is_search_service_process(pid: int) -> bool:
    command = _process_command(pid).lower()
    if not command:
        return False
    return any(marker in command for marker in _PROCESS_MARKERS)


def list_search_service_pids(port: int) -> list[int]:
    """返回监听指定端口且属于 EverythingSearch 的进程 PID。"""
    result = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []

    pids: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pid = int(line)
        except ValueError:
            continue
        if _is_search_service_process(pid):
            pids.append(pid)
    return sorted(set(pids))


def capture_search_service_snapshot(port: int) -> SearchServiceSnapshot:
    """记录当前搜索服务是否在运行。"""
    service = resolve_launchd_app_service()
    pids = list_search_service_pids(port)
    return SearchServiceSnapshot(
        launchd_was_loaded=is_launchd_job_loaded(service),
        service_was_running=bool(pids),
    )


def _wait_port_listeners_gone(port: int, timeout_sec: float = 15.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not list_search_service_pids(port):
            return
        time.sleep(0.5)
    raise RuntimeError("停止搜索服务超时，请稍后手动重启搜索服务。")


def _terminate_pids(pids: list[int]) -> None:
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue

    deadline = time.time() + 10.0
    while time.time() < deadline:
        alive = [pid for pid in pids if _pid_exists(pid)]
        if not alive:
            return
        time.sleep(0.5)

    for pid in pids:
        if _pid_exists(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                continue


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def _bootout_launchd_if_loaded(service: LaunchdAppService) -> bool:
    if not is_launchd_job_loaded(service):
        return False
    result = subprocess.run(
        ["launchctl", "bootout", service.job_target],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"停止搜索服务失败: {stderr or result.returncode}")
    if is_launchd_job_loaded(service):
        raise RuntimeError("停止搜索服务失败，请稍后重试。")
    return True


def _bootstrap_launchd_if_needed(service: LaunchdAppService) -> None:
    if not service.plist_path.is_file():
        return
    if is_launchd_job_loaded(service):
        return
    result = subprocess.run(
        ["launchctl", "bootstrap", service.bootstrap_domain, str(service.plist_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"启动搜索服务失败: {stderr or result.returncode}")


def stop_search_service(port: int) -> SearchServiceSnapshot:
    """停止搜索服务，返回停止前状态。"""
    snapshot = capture_search_service_snapshot(port)
    if not snapshot.service_was_running and not snapshot.launchd_was_loaded:
        return snapshot

    logger.info("正在停止搜索服务...")
    service = resolve_launchd_app_service()
    _bootout_launchd_if_loaded(service)

    pids = list_search_service_pids(port)
    if pids:
        _terminate_pids(pids)
        _wait_port_listeners_gone(port)

    logger.info("搜索服务已停止。")
    return snapshot


def restart_search_service(port: int, snapshot: SearchServiceSnapshot | None = None) -> bool:
    """重启或启动搜索服务以加载新索引。返回是否已成功拉起服务。"""
    snapshot = snapshot or capture_search_service_snapshot(port)
    service = resolve_launchd_app_service()
    has_plist = service.plist_path.is_file()

    should_manage = (
        snapshot.service_was_running
        or snapshot.launchd_was_loaded
        or has_plist
    )
    if not should_manage:
        logger.info("索引已更新。请重新启动搜索服务以加载新数据。")
        return False

    logger.info("正在重启搜索服务...")
    service = resolve_launchd_app_service()

    if service.plist_path.is_file():
        _bootstrap_launchd_if_needed(service)
        pids = list_search_service_pids(port)
        if pids:
            _terminate_pids(pids)
            _wait_port_listeners_gone(port, timeout_sec=10.0)

        result = subprocess.run(
            ["launchctl", "kickstart", "-k", service.job_target],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"重启搜索服务失败: {stderr or result.returncode}")

        deadline = time.time() + 20.0
        while time.time() < deadline:
            if list_search_service_pids(port):
                logger.info("搜索服务已就绪。")
                return True
            time.sleep(0.5)
        raise RuntimeError("重启搜索服务超时，请手动重新启动搜索服务。")

    pids = list_search_service_pids(port)
    if pids:
        _terminate_pids(pids)
        _wait_port_listeners_gone(port, timeout_sec=10.0)

    logger.info("索引已更新。请重新启动搜索服务以加载新数据。")
    return False


@contextmanager
def suspend_search_service_for_rebuild(port: int) -> Iterator[SearchServiceSnapshot]:
    """全量重建期间暂停搜索服务，结束后自动恢复。"""
    snapshot = stop_search_service(port)
    try:
        yield snapshot
    finally:
        if snapshot.service_was_running or snapshot.launchd_was_loaded:
            restart_search_service(port, snapshot)
