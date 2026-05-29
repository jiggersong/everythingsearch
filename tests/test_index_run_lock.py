"""索引互斥锁测试。"""

from __future__ import annotations

import multiprocessing
import os
import time

from everythingsearch.infra.index_run_lock import IndexRunLock, read_index_run_lock_holder


def _hold_lock(lock_path: str, ready_event, release_event) -> None:
    lock = IndexRunLock(lock_path, "incremental")
    assert lock.try_acquire()
    ready_event.set()
    release_event.wait(timeout=5)
    lock.release()


def test_index_run_lock_blocks_second_acquire(tmp_path):
    lock_path = str(tmp_path / "index_run.lock")
    first = IndexRunLock(lock_path, "incremental")
    second = IndexRunLock(lock_path, "full")

    assert first.try_acquire()
    assert not second.try_acquire()

    holder = read_index_run_lock_holder(lock_path)
    assert holder is not None
    assert holder.pid == os.getpid()
    assert holder.run_mode == "incremental"

    first.release()
    assert second.try_acquire()
    second.release()


def test_index_run_lock_released_by_other_process(tmp_path):
    lock_path = str(tmp_path / "index_run.lock")
    ready = multiprocessing.Event()
    release = multiprocessing.Event()

    worker = multiprocessing.Process(
        target=_hold_lock,
        args=(lock_path, ready, release),
    )
    worker.start()
    try:
        assert ready.wait(timeout=5)
        blocker = IndexRunLock(lock_path, "full")
        assert not blocker.try_acquire()
        release.set()
        worker.join(timeout=5)
        assert worker.exitcode == 0

        waiter = IndexRunLock(lock_path, "full")
        deadline = time.time() + 3
        acquired = False
        while time.time() < deadline:
            if waiter.try_acquire():
                acquired = True
                break
            time.sleep(0.05)
        assert acquired
        waiter.release()
    finally:
        if worker.is_alive():
            release.set()
            worker.join(timeout=2)


def test_index_run_lock_context_manager(tmp_path):
    lock_path = str(tmp_path / "index_run.lock")
    with IndexRunLock(lock_path, "incremental") as lock:
        assert lock.acquired
        assert read_index_run_lock_holder(lock_path) is not None

    follow_up = IndexRunLock(lock_path, "incremental")
    assert follow_up.try_acquire()
    follow_up.release()
