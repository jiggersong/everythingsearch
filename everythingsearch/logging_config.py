"""按天滚动的文件日志（午夜切分，归档名带日期后缀）。"""

from __future__ import annotations

import logging
import logging.handlers
import os

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
    """Flask 开发入口（python -m everythingsearch.app）写入 logs/，按天滚动。

    终端与日志文件完全隔离，所有日志仅写入文件。
    """
    attach_timed_rotating_file("everythingsearch", "app_dev.log", level=logging.INFO)
    attach_timed_rotating_file(
        "werkzeug",
        "werkzeug_dev.log",
        level=logging.INFO,
        fmt="%(message)s",
    )

    # 防止未配置的 root logger 通过 lastResort 向 stderr 泄漏 WARNING+
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.NullHandler())


def setup_cli_logging(*, level: int = logging.INFO) -> None:
    """CLI 任务（增量/全量索引）日志配置。

    终端与日志文件完全隔离：
    - 所有日志（INFO+）仅写入按天滚动的 ``logs/cli.log``。
    - 终端不输出任何日志内容，用户友好的进度信息由调用方通过 ``print()`` 负责。
    - 压低 chromadb/httpx 等第三方库噪音。
    """
    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    log_dir = log_directory()
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "cli.log")

    # 清理 root logger 上的旧 handler，以 root 为唯一日志出口
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)

    # 文件 handler 挂载到 root logger，确保所有模块（含 __main__）的日志统一写入文件
    # 检查是否已存在相同路径的 handler，避免重复挂接
    if _logger_has_daily_handler_for_path(root, log_path):
        return

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=90,
        encoding="utf-8",
        delay=True,
    )
    setattr(file_handler, _MARK, True)
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    root.addHandler(file_handler)
    root.setLevel(level)

    # 终端不输出任何日志：用户反馈全部由 print() 负责

    for name in (
        "chromadb",
        "chromadb.telemetry",
        "httpx",
        "httpcore",
        "urllib3",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
