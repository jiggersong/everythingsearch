"""按天滚动的文件日志（午夜切分，归档名带日期后缀）。"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys

from .infra.paths import get_project_root

_MARK = "_everythingsearch_daily_log"


def _project_root() -> str:
    return str(get_project_root())


def log_directory() -> str:
    return os.path.join(_project_root(), "logs")


def _logger_has_daily_handler_for_path(logger: logging.Logger, log_path: str) -> bool:
    normalized_path = os.path.abspath(log_path)
    for handler in logger.handlers:
        if not getattr(handler, _MARK, False):
            continue
        if os.path.abspath(getattr(handler, "baseFilename", "")) == normalized_path:
            return True
    return False


def attach_timed_rotating_file(
    logger_name: str,
    relative_filename: str,
    *,
    level: int = logging.INFO,
    backup_count: int = 90,
    fmt: str = "%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt: str = "%Y-%m-%d %H:%M:%S",
) -> None:
    log_dir = log_directory()
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(logger_name)
    path = os.path.join(log_dir, relative_filename)
    if _logger_has_daily_handler_for_path(logger, path):
        return
    handler = logging.handlers.TimedRotatingFileHandler(
        path,
        when="midnight",
        interval=1,
        backupCount=backup_count,
        encoding="utf-8",
        delay=True,
    )
    setattr(handler, _MARK, True)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    logger.addHandler(handler)
    logger.setLevel(level)


def setup_flask_dev_daily_file_logging() -> None:
    """Flask 开发入口（python -m everythingsearch.app）写入 logs/，按天滚动。"""
    attach_timed_rotating_file("everythingsearch", "app_dev.log", level=logging.INFO)
    attach_timed_rotating_file(
        "werkzeug",
        "werkzeug_dev.log",
        level=logging.INFO,
        fmt="%(message)s",
    )


def setup_cli_logging(*, level: int = logging.INFO) -> None:
    """CLI 任务（增量/全量索引）日志配置。

    终端输出与日志文件分离：
    - 详细日志（INFO+）写入按天滚动的 ``logs/cli.log``。
    - 终端仅输出 WARNING+ 到 stderr，避免 INFO 日志刷屏。
    - 用户友好的进度信息由调用方通过 ``print()`` 直接输出。
    - 压低 chromadb/httpx 等第三方库噪音。
    """
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # 文件日志：完整 INFO+ 信息写入 cli.log
    log_es = logging.getLogger("everythingsearch")
    log_es.setLevel(level)
    attach_timed_rotating_file(
        "everythingsearch",
        "cli.log",
        level=level,
        fmt=fmt,
        datefmt=datefmt,
    )

    # 终端：仅 WARNING+ 输出到 stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    for h in root.handlers[:]:
        root.removeHandler(h)
    root.addHandler(stderr_handler)

    for name in (
        "chromadb",
        "chromadb.telemetry",
        "httpx",
        "httpcore",
        "urllib3",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
