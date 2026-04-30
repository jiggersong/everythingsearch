"""索引任务进度与成本日志输出。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import logging
import threading
import time
from collections.abc import Callable, Iterator

from everythingsearch.indexing.progress_estimator import IndexCostEstimate


@dataclass
class IndexProgressState:
    """索引任务运行时进度状态。"""

    phase_name: str
    total_file_count: int
    pending_file_count: int
    estimated_total_chunk_count: int
    estimated_total_token_count: int
    processed_file_count: int = 0
    scanned_file_count: int = 0
    deleted_file_count: int = 0
    written_sparse_chunk_count: int = 0
    written_dense_chunk_count: int = 0
    processed_token_count: int = 0
    embedding_cache_hit_text_count: int = 0
    embedding_uncached_text_count: int = 0
    embedding_remote_batch_count: int = 0
    skipped_file_count: int = 0
    failed_file_count: int = 0


class IndexProgressReporter:
    """索引任务进度与成本日志输出器。"""

    def __init__(
        self,
        task_name: str,
        logger: logging.Logger,
        interval_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds 必须大于 0")
        self._task_name = task_name
        self._logger = logger
        self._interval_seconds = interval_seconds
        self._clock = clock
        self._state: IndexProgressState | None = None
        self._start_time = 0.0
        self._last_report_time = 0.0
        self._lock = threading.Lock()
        self._ticker_stop = threading.Event()
        self._ticker_thread: threading.Thread | None = None

    def start(self, initial_state: IndexProgressState, estimate: IndexCostEstimate) -> None:
        """输出启动提示并初始化进度状态。

        Args:
            initial_state: 初始运行状态。
            estimate: 启动成本估算。
        """
        now = self._clock()
        self._state = initial_state
        self._start_time = now
        self._last_report_time = now

        # 终端：简洁标题
        _print_separator()
        print(f"  {self._task_name}")
        _print_separator()

        # 日志：完整预估信息
        self._logger.info("%s 开始，预估: 待处理文件=%s, 预计索引块=%s, "
                          "预计输入 Token=%s, 预计远端 embedding 文本=%s, "
                          "预计耗时=%s, 可信度=%s",
                          self._task_name,
                          initial_state.pending_file_count,
                          estimate.estimated_chunk_count,
                          estimate.estimated_input_token_count,
                          estimate.estimated_remote_embedding_text_count,
                          format_duration(estimate.estimated_total_seconds),
                          estimate.confidence_level)
        for note in estimate.notes:
            self._logger.info("预估说明: %s", note)

    def update_phase(self, phase_name: str) -> None:
        """更新当前阶段名称。"""
        if self._state is None:
            return
        with self._lock:
            self._state.phase_name = phase_name
        self.maybe_report()

    def update_estimate(self, estimate: IndexCostEstimate) -> None:
        """用更准确的估算刷新总 chunk 与 Token 数（仅写日志）。"""
        if self._state is None:
            return
        with self._lock:
            self._state.estimated_total_chunk_count = estimate.estimated_chunk_count
            self._state.estimated_total_token_count = estimate.estimated_input_token_count
        self._logger.info(
            "预估已修正: 预计索引块=%s, 预计输入 Token=%s, 预计远端 embedding 文本=%s, 预计耗时=%s",
            estimate.estimated_chunk_count,
            estimate.estimated_input_token_count,
            estimate.estimated_remote_embedding_text_count,
            format_duration(estimate.estimated_total_seconds),
        )

    def add_processed_file(self, chunk_count: int, estimated_token_count: int) -> None:
        """记录一个文件处理完成（Dense + Sparse 写入完成）。"""
        if self._state is None:
            return
        safe_chunk_count = max(0, chunk_count)
        safe_token_count = max(0, estimated_token_count)
        with self._lock:
            self._state.processed_file_count += 1
            self._state.processed_token_count += safe_token_count
            if safe_chunk_count > 0:
                self._state.estimated_total_chunk_count = max(
                    self._state.estimated_total_chunk_count,
                    self._state.written_sparse_chunk_count + safe_chunk_count,
                    self._state.written_dense_chunk_count + safe_chunk_count,
                )
        self.maybe_report()

    def add_scanned_file(self, chunk_count: int, estimated_token_count: int) -> None:
        """记录一个文件扫描完成（尚未写入索引）。"""
        if self._state is None:
            return
        safe_chunk_count = max(0, chunk_count)
        safe_token_count = max(0, estimated_token_count)
        with self._lock:
            self._state.scanned_file_count += 1
            self._state.processed_token_count += safe_token_count
            if safe_chunk_count > 0:
                self._state.estimated_total_chunk_count = max(
                    self._state.estimated_total_chunk_count,
                    self._state.scanned_file_count * safe_chunk_count,
                )
        self.maybe_report()

    def scanning_complete(self) -> None:
        """扫描阶段结束，将已扫描文件数同步为已处理文件数。"""
        if self._state is None:
            return
        with self._lock:
            self._state.processed_file_count = self._state.scanned_file_count
        self.maybe_report()

    def add_deleted_files(self, file_count: int) -> None:
        """按批次记录已删除索引的文件数量。"""
        if self._state is None:
            return
        with self._lock:
            self._state.deleted_file_count += max(0, file_count)
        self.maybe_report()

    def add_sparse_chunks(self, chunk_count: int) -> None:
        """记录 Sparse 写入数量。"""
        if self._state is None:
            return
        with self._lock:
            self._state.written_sparse_chunk_count += max(0, chunk_count)
        self.maybe_report()

    def add_dense_chunks(self, chunk_count: int) -> None:
        """记录 Dense 写入数量。"""
        if self._state is None:
            return
        with self._lock:
            self._state.written_dense_chunk_count += max(0, chunk_count)
        self.maybe_report()

    def set_embedding_stats(
        self,
        cache_hits: int,
        uncached_texts: int,
        remote_batches: int = 0,
    ) -> None:
        """同步 embedding 缓存与远端文本统计。"""
        if self._state is None:
            return
        with self._lock:
            self._state.embedding_cache_hit_text_count = max(0, cache_hits)
            self._state.embedding_uncached_text_count = max(0, uncached_texts)
            self._state.embedding_remote_batch_count = max(0, remote_batches)
        self.maybe_report()

    def add_skipped_file(self) -> None:
        """记录跳过文件。"""
        if self._state is None:
            return
        with self._lock:
            self._state.skipped_file_count += 1
        self.maybe_report()

    def add_failed_file(self) -> None:
        """记录失败文件。"""
        if self._state is None:
            return
        with self._lock:
            self._state.failed_file_count += 1
        self.maybe_report()

    def maybe_report(self) -> None:
        """若距离上次输出已超过间隔，则输出一次进度。"""
        if self._state is None:
            return
        now = self._clock()
        if now - self._last_report_time < self._interval_seconds:
            return
        self._last_report_time = now
        self._report_progress(now)

    @contextmanager
    def blocking_phase(self, phase_name: str) -> Iterator[None]:
        """进入可能长时间无业务回调的阶段时，临时启用后台 ticker。"""
        self.update_phase(phase_name)
        self._start_ticker()
        try:
            yield
        finally:
            self._stop_ticker()

    def finish(self) -> None:
        """停止可选后台 ticker 并输出总结报告。"""
        self._stop_ticker()
        if self._state is None:
            return
        elapsed = self._clock() - self._start_time
        state = self._snapshot()

        # 终端：简洁汇总
        print(f"  {'─' * 46}")
        print(f"  结果: 成功 {state.processed_file_count}"
              f"  删除 {state.deleted_file_count}"
              f"  跳过 {state.skipped_file_count}"
              f"  失败 {state.failed_file_count}")
        print(f"  耗时: {format_duration(elapsed)}")
        _print_separator()

        # 日志：完整指标
        self._logger.info(
            "%s完成: 总耗时=%s, 扫描文件=%s, 成功处理文件=%s, 删除文件=%s, 跳过文件=%s, 失败文件=%s, "
            "Sparse 索引块=%s, Dense 索引块=%s, 估算输入 Token=%s, "
            "embedding 缓存命中=%s, 远端 embedding 文本=%s, 远端批次=%s",
            self._task_name,
            format_duration(elapsed),
            state.scanned_file_count,
            state.processed_file_count,
            state.deleted_file_count,
            state.skipped_file_count,
            state.failed_file_count,
            state.written_sparse_chunk_count,
            state.written_dense_chunk_count,
            state.processed_token_count,
            state.embedding_cache_hit_text_count,
            state.embedding_uncached_text_count,
            state.embedding_remote_batch_count,
        )

    def _start_ticker(self) -> None:
        if self._ticker_thread and self._ticker_thread.is_alive():
            return
        self._ticker_stop.clear()
        self._ticker_thread = threading.Thread(
            target=self._run_ticker,
            name=f"{self._task_name}-progress",
            daemon=True,
        )
        self._ticker_thread.start()

    def _stop_ticker(self) -> None:
        if not self._ticker_thread:
            return
        self._ticker_stop.set()
        self._ticker_thread.join(timeout=2.0)
        self._ticker_thread = None

    def _run_ticker(self) -> None:
        while not self._ticker_stop.wait(self._interval_seconds):
            if self._state is None:
                return
            self._last_report_time = self._clock()
            self._report_progress(self._last_report_time)

    def _snapshot(self) -> IndexProgressState:
        with self._lock:
            assert self._state is not None
            return IndexProgressState(**self._state.__dict__)

    def _report_progress(self, now: float) -> None:
        state = self._snapshot()
        elapsed = max(0.0, now - self._start_time)
        is_scan_phase = "扫描" in state.phase_name
        if is_scan_phase:
            file_done = state.scanned_file_count
            file_label = "已扫描"
        else:
            file_done = state.processed_file_count + state.deleted_file_count
            file_label = "已处理"
        remaining_files = max(0, state.pending_file_count - file_done)
        remaining_tokens = max(0, state.estimated_total_token_count - state.processed_token_count)
        remaining_seconds = estimate_remaining_seconds(
            elapsed,
            max(file_done, 1),
            remaining_files,
        )
        progress_pct = calculate_percent(file_done, state.pending_file_count)

        # 终端：简洁进度行
        remaining_str = format_duration(remaining_seconds) if remaining_seconds is not None else "计算中"
        print(f"  {file_label} [{progress_pct:5.1f}%] {file_done}/{state.pending_file_count}"
              f"  已耗时: {format_duration(elapsed)}"
              f"  预计剩余: {remaining_str}")

        # 日志：完整指标
        self._logger.info(
            "索引进度: 阶段=%s, 已耗时=%s, %s=%s/%s (%.1f%%), "
            "已写入 Sparse=%s, 已写入 Dense=%s, 已估算 Token=%s/%s, "
            "缓存命中=%s, 远端 embedding 文本=%s, 剩余文件=%s, 预计剩余耗时=%s, 预计剩余 Token=%s",
            state.phase_name,
            format_duration(elapsed),
            file_label,
            file_done,
            state.pending_file_count,
            progress_pct,
            state.written_sparse_chunk_count,
            state.written_dense_chunk_count,
            state.processed_token_count,
            state.estimated_total_token_count,
            state.embedding_cache_hit_text_count,
            state.embedding_uncached_text_count,
            remaining_files,
            format_duration(remaining_seconds) if remaining_seconds is not None else "未知",
            remaining_tokens,
        )


def _print_separator() -> None:
    """打印终端分隔线。"""
    print("=" * 50)


def calculate_percent(done: int, total: int) -> float:
    """计算百分比，避免除零。"""
    if total <= 0:
        return 100.0
    return min(100.0, max(0.0, done / total * 100))


def estimate_remaining_seconds(
    elapsed_seconds: float,
    processed_file_count: int,
    remaining_file_count: int,
) -> float | None:
    """按当前文件处理速度估算剩余秒数。"""
    if processed_file_count <= 0 or remaining_file_count <= 0:
        return None if remaining_file_count > 0 else 0.0
    seconds_per_file = elapsed_seconds / processed_file_count
    return remaining_file_count * seconds_per_file


def format_duration(seconds: float) -> str:
    """格式化秒数为紧凑中文耗时。"""
    safe_seconds = max(0, int(round(seconds)))
    if safe_seconds < 60:
        return f"{safe_seconds}s"
    minutes, second = divmod(safe_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {second}s"
    hours, minute = divmod(minutes, 60)
    return f"{hours}h {minute}m"
