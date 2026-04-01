"""测试日志配置与日志标准化约束。"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from everythingsearch import logging_config

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _count_console_marks(logger: logging.Logger) -> int:
    return sum(
        1 for handler in logger.handlers
        if getattr(handler, logging_config._CONSOLE_MARK, False)
    )


def _count_daily_marks(logger: logging.Logger) -> int:
    return sum(
        1 for handler in logger.handlers
        if getattr(handler, logging_config._MARK, False)
    )


class TestLoggingConfig:
    """测试日志配置。"""

    def test_setup_cli_logging_does_not_duplicate_handlers(self):
        """CLI 日志初始化不应重复挂接 handler。"""
        logger = logging.getLogger("everythingsearch")
        original_handlers = list(logger.handlers)
        original_level = logger.level
        try:
            logger.handlers = []
            logger.setLevel(logging.NOTSET)

            logging_config.setup_cli_logging()
            logging_config.setup_cli_logging()

            assert _count_console_marks(logger) == 1
            assert _count_daily_marks(logger) == 1
        finally:
            logger.handlers = original_handlers
            logger.setLevel(original_level)

    def test_cli_logging_can_attach_separate_file_after_flask_logging(self):
        """同一 logger 上应允许挂接不同文件的日滚动 handler。"""
        logger = logging.getLogger("everythingsearch")
        original_handlers = list(logger.handlers)
        original_level = logger.level
        try:
            logger.handlers = []
            logger.setLevel(logging.NOTSET)

            logging_config.setup_flask_dev_daily_file_logging()
            logging_config.setup_cli_logging()

            filenames = sorted(
                Path(handler.baseFilename).name
                for handler in logger.handlers
                if getattr(handler, logging_config._MARK, False)
            )
            assert filenames == ["app_dev.log", "cli.log"]
        finally:
            logger.handlers = original_handlers
            logger.setLevel(original_level)


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

    def test_incremental_has_no_print_calls(self):
        """incremental 核心路径源码不应再包含 print 调用。"""
        source = (_PROJECT_ROOT / "everythingsearch" / "incremental.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "print"
            for node in ast.walk(tree)
        )
