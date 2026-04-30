"""测试日志配置与日志标准化约束。"""

from __future__ import annotations

import ast
import logging
import sys
from pathlib import Path

from everythingsearch import logging_config

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _count_root_stream_handlers() -> int:
    return sum(1 for h in logging.root.handlers if isinstance(h, logging.StreamHandler))


def _count_root_stderr_handlers() -> int:
    return sum(
        1 for h in logging.root.handlers
        if isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stderr
    )


def _count_daily_marks(logger: logging.Logger) -> int:
    return sum(
        1 for handler in logger.handlers
        if getattr(handler, logging_config._MARK, False)
    )


class TestLoggingConfig:
    """测试日志配置。"""

    def test_setup_cli_logging_does_not_duplicate_handlers(self):
        """CLI 日志初始化不应重复挂接 handler，且仅有文件 handler 无 stream handler。"""
        logger = logging.getLogger("everythingsearch")
        original_es_handlers = list(logger.handlers)
        original_es_level = logger.level
        original_root_handlers = list(logging.root.handlers)
        original_root_level = logging.root.level
        try:
            logger.handlers = []
            logger.setLevel(logging.NOTSET)
            logging.root.handlers = []
            logging.root.setLevel(logging.WARNING)

            logging_config.setup_cli_logging()
            logging_config.setup_cli_logging()

            # 终端不应有任何输出到 stderr 的 handler
            assert _count_root_stderr_handlers() == 0
            # 文件 handler 挂载在 root logger，重复调用不重复挂接
            assert _count_daily_marks(logging.root) == 1
        finally:
            logger.handlers = original_es_handlers
            logger.setLevel(original_es_level)
            logging.root.handlers = original_root_handlers
            logging.root.setLevel(original_root_level)

    def test_cli_logging_can_attach_separate_file_after_flask_logging(self):
        """Flask 和 CLI 日志配置应各自挂接 handler 到正确的 logger 上。"""
        logger = logging.getLogger("everythingsearch")
        original_es_handlers = list(logger.handlers)
        original_es_level = logger.level
        original_root_handlers = list(logging.root.handlers)
        original_root_level = logging.root.level
        try:
            logger.handlers = []
            logger.setLevel(logging.NOTSET)
            logging.root.handlers = []
            logging.root.setLevel(logging.WARNING)

            logging_config.setup_flask_dev_daily_file_logging()
            logging_config.setup_cli_logging()

            # everythingsearch logger 上应有 Flask 的 app_dev.log
            es_filenames = sorted(
                Path(handler.baseFilename).name
                for handler in logger.handlers
                if getattr(handler, logging_config._MARK, False)
            )
            assert es_filenames == ["app_dev.log"]

            # root logger 上应有 CLI 的 cli.log
            root_filenames = sorted(
                Path(handler.baseFilename).name
                for handler in logging.root.handlers
                if getattr(handler, logging_config._MARK, False)
            )
            assert root_filenames == ["cli.log"]
        finally:
            logger.handlers = original_es_handlers
            logger.setLevel(original_es_level)
            logging.root.handlers = original_root_handlers
            logging.root.setLevel(original_root_level)


class TestLoggingPrintUsage:
    """测试核心路径不再使用 print。"""

    def test_indexer_has_no_print_calls(self):
        """indexer 核心路径源码不应再包含 print 调用。"""
        source = (_PROJECT_ROOT / "everythingsearch" / "indexer.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
            for node in ast.walk(tree)
        )


class TestConfigImportUsage:
    """测试已迁移模块不再直接依赖 config。"""

    def test_migrated_modules_have_no_direct_config_import(self):
        migrated_modules = [
            _PROJECT_ROOT / "everythingsearch" / "app.py",
            _PROJECT_ROOT / "everythingsearch" / "file_access.py",
            _PROJECT_ROOT / "everythingsearch" / "logging_config.py",
            _PROJECT_ROOT / "everythingsearch" / "services" / "file_service.py",
            _PROJECT_ROOT / "everythingsearch" / "services" / "search_service.py",
        ]

        for module_path in migrated_modules:
            tree = ast.parse(module_path.read_text(encoding="utf-8"))
            has_direct_config_import = any(
                isinstance(node, ast.Import)
                and any(alias.name == "config" for alias in node.names)
                for node in ast.walk(tree)
            ) or any(
                isinstance(node, ast.ImportFrom)
                and node.module == "config"
                for node in ast.walk(tree)
            )
            assert has_direct_config_import is False, module_path.name

    def test_incremental_uses_print_for_terminal_and_logger_for_file(self):
        """incremental 源码应同时使用 print（终端友好输出）和 logger（文件日志）。"""
        source = (_PROJECT_ROOT / "everythingsearch" / "incremental.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        calls = [
            (node.lineno, node.func.id)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("print",)
        ]
        assert calls, "incremental.py 应包含 print() 调用用于终端友好输出"
