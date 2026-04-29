"""索引进度 reporter 测试。"""

from __future__ import annotations

import logging
import time

from everythingsearch.indexing.progress_estimator import IndexCostEstimate
from everythingsearch.indexing.progress_reporter import (
    IndexProgressReporter,
    IndexProgressState,
    calculate_percent,
    estimate_remaining_seconds,
    format_duration,
)


class ListHandler(logging.Handler):
    """收集日志记录的测试 handler。"""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class MutableClock:
    """可控时钟。"""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class TestIndexProgressReporter:
    """测试进度日志输出器。"""

    def test_start_outputs_initial_estimate(self):
        """start() 应输出任务说明与成本预估。"""
        reporter, handler, _clock = _build_reporter()

        reporter.start(_state(), _estimate())

        assert any("增量索引更新 开始" in message for message in handler.messages)
        assert any("预计输入 Token=200" in message for message in handler.messages)

    def test_maybe_report_is_interval_limited(self):
        """未到 30 秒时不应重复输出进度。"""
        reporter, handler, clock = _build_reporter()
        reporter.start(_state(), _estimate())

        clock.value = 29.0
        reporter.add_processed_file(chunk_count=1, estimated_token_count=10)
        assert not any("索引进度:" in message for message in handler.messages)

        clock.value = 30.0
        reporter.add_processed_file(chunk_count=1, estimated_token_count=10)
        assert any("索引进度:" in message for message in handler.messages)

    def test_deleted_files_count_toward_progress(self):
        """删除文件应计入整体处理进度。"""
        reporter, handler, clock = _build_reporter()
        reporter.start(_state(pending_file_count=2), _estimate())

        clock.value = 30.0
        reporter.add_deleted_files(1)

        assert any("已处理文件=1/2" in message for message in handler.messages)

    def test_finish_outputs_summary(self):
        """finish() 应输出完成总结。"""
        reporter, handler, clock = _build_reporter()
        reporter.start(_state(), _estimate())
        clock.value = 10.0
        reporter.add_processed_file(chunk_count=1, estimated_token_count=20)
        reporter.add_sparse_chunks(1)
        reporter.add_dense_chunks(1)
        reporter.set_embedding_stats(2, 3, 1)

        reporter.finish()

        assert any("增量索引更新完成" in message for message in handler.messages)
        assert any("远端 embedding 文本=3" in message for message in handler.messages)

    def test_blocking_phase_stops_ticker(self):
        """阻塞阶段退出后应清理后台 ticker。"""
        reporter, _handler, _clock = _build_reporter(interval_seconds=0.01)
        reporter.start(_state(), _estimate())

        with reporter.blocking_phase("Dense Index 写入"):
            time.sleep(0.02)

        assert reporter._ticker_thread is None

    def test_add_scanned_file_does_not_affect_processed_count(self):
        """扫描阶段应只增加 scanned_file_count，不影响 processed_file_count。"""
        reporter, handler, clock = _build_reporter()
        reporter.start(_state(pending_file_count=4), _estimate())

        reporter.add_scanned_file(chunk_count=2, estimated_token_count=10)

        assert reporter._state.scanned_file_count == 1
        assert reporter._state.processed_file_count == 0

    def test_scanning_complete_transfers_scanned_to_processed(self):
        """scanning_complete 应将已扫描文件数同步为已处理文件数。"""
        reporter, handler, clock = _build_reporter()
        reporter.start(_state(pending_file_count=4), _estimate())

        reporter.add_scanned_file(chunk_count=1, estimated_token_count=10)
        reporter.add_scanned_file(chunk_count=1, estimated_token_count=10)
        reporter.scanning_complete()

        assert reporter._state.processed_file_count == 2
        assert reporter._state.scanned_file_count == 2

    def test_scan_phase_shows_scanned_label(self):
        """扫描阶段进度应显示"已扫描文件"而非"已处理文件"。"""
        reporter, handler, clock = _build_reporter()
        state = _state(pending_file_count=4)
        state.phase_name = "扫描与解析文件"
        reporter.start(state, _estimate())

        clock.value = 30.0
        reporter.add_scanned_file(chunk_count=1, estimated_token_count=10)

        assert any("已扫描文件=1/4" in message for message in handler.messages)
        assert not any("已处理文件=1/4" in message for message in handler.messages)


def test_calculate_percent_handles_zero_total():
    """百分比工具应避免除零。"""
    assert calculate_percent(0, 0) == 100.0


def test_estimate_remaining_seconds_handles_zero_progress():
    """无进度但有剩余时 ETA 应未知。"""
    assert estimate_remaining_seconds(30.0, 0, 10) is None
    assert estimate_remaining_seconds(30.0, 5, 5) == 30.0


def test_format_duration():
    """耗时格式化应保持紧凑。"""
    assert format_duration(5) == "5s"
    assert format_duration(65) == "1m 5s"
    assert format_duration(3660) == "1h 1m"


def _build_reporter(interval_seconds: float = 30.0):
    logger = logging.getLogger(f"test-progress-{time.time_ns()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = ListHandler()
    logger.addHandler(handler)
    clock = MutableClock()
    reporter = IndexProgressReporter(
        "增量索引更新",
        logger,
        interval_seconds=interval_seconds,
        clock=clock,
    )
    return reporter, handler, clock


def _state(pending_file_count: int = 4) -> IndexProgressState:
    return IndexProgressState(
        phase_name="准备",
        total_file_count=pending_file_count,
        pending_file_count=pending_file_count,
        estimated_total_chunk_count=8,
        estimated_total_token_count=200,
    )


def _estimate() -> IndexCostEstimate:
    return IndexCostEstimate(
        estimated_chunk_count=8,
        estimated_input_token_count=200,
        estimated_remote_embedding_text_count=8,
        estimated_total_seconds=12.0,
        confidence_level="low",
    )
