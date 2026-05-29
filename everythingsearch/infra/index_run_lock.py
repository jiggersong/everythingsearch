"""索引进程互斥锁，防止定时任务与手动索引并发执行。"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

IndexRunMode = Literal["incremental", "full"]


@dataclass(frozen=True)
class IndexRunLockHolder:
    """当前锁持有者信息。"""

    pid: int
    run_mode: IndexRunMode
    started_at: float


def read_index_run_lock_holder(lock_path: str) -> IndexRunLockHolder | None:
    """读取锁文件中的持有者信息（不获取锁）。"""
    if not os.path.isfile(lock_path):
        return None
    try:
        with open(lock_path, encoding="utf-8") as handle:
            payload = json.load(handle)
        return IndexRunLockHolder(
            pid=int(payload["pid"]),
            run_mode=str(payload["run_mode"]),  # type: ignore[arg-type]
            started_at=float(payload["started_at"]),
        )
    except (OSError, TypeError, ValueError, KeyError):
        return None


class IndexRunLock:
    """基于 flock 的跨进程索引互斥锁。"""

    def __init__(self, lock_path: str, run_mode: IndexRunMode) -> None:
        self._lock_path = lock_path
        self._run_mode = run_mode
        self._fd: int | None = None

    @property
    def acquired(self) -> bool:
        return self._fd is not None

    def try_acquire(self) -> bool:
        """非阻塞获取锁；已有其他存活进程持锁时返回 False。"""
        if self._fd is not None:
            return True

        lock_dir = os.path.dirname(self._lock_path)
        if lock_dir:
            os.makedirs(lock_dir, exist_ok=True)

        fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            holder = read_index_run_lock_holder(self._lock_path)
            if holder is not None:
                logger.warning(
                    "索引锁已被占用: pid=%s mode=%s started_at=%.0f",
                    holder.pid,
                    holder.run_mode,
                    holder.started_at,
                )
            else:
                logger.warning("索引锁已被占用（无法读取锁文件详情）。")
            return False

        payload = json.dumps(
            {
                "pid": os.getpid(),
                "run_mode": self._run_mode,
                "started_at": time.time(),
            },
            ensure_ascii=False,
        )
        os.ftruncate(fd, 0)
        os.write(fd, payload.encode("utf-8"))
        os.fsync(fd)
        self._fd = fd
        return True

    def release(self) -> None:
        """释放锁并关闭文件描述符。"""
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> IndexRunLock:
        if not self.try_acquire():
            raise IndexRunLockBusyError(self._lock_path)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class IndexRunLockBusyError(RuntimeError):
    """索引锁已被其他进程占用。"""
