"""索引任务轻量文件盘点模块。"""

from __future__ import annotations

import os

from everythingsearch.indexer import normalize_path
from everythingsearch.infra.settings import get_settings, require_target_dirs


def scan_disk_files_for_index() -> dict[str, tuple[float, str]]:
    """扫描普通索引目录，返回文件路径到 mtime/source_type 的映射。

    Returns:
        dict[str, tuple[float, str]]: `{filepath: (mtime, "file")}` 映射。

    Raises:
        MissingRequiredSettingError: 未配置 TARGET_DIR 时由 `require_target_dirs` 抛出。

    Core logic:
        只遍历目录、过滤隐藏文件和不支持的扩展名、读取 mtime；不读取文件正文，
        用于索引任务开始前的规模判断。
    """
    settings = get_settings()
    result: dict[str, tuple[float, str]] = {}
    for target_dir in require_target_dirs(settings):
        if not os.path.isdir(target_dir):
            continue
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [dirname for dirname in dirs if not dirname.startswith(".")]
            for filename in files:
                if filename.startswith("."):
                    continue
                _, ext = os.path.splitext(filename)
                if ext.lower() not in settings.supported_extensions:
                    continue
                filepath = normalize_path(os.path.join(root, filename))
                if settings.index_only_keywords and not any(
                    keyword in filepath for keyword in settings.index_only_keywords
                ):
                    continue
                try:
                    mtime = os.path.getmtime(filepath)
                except OSError:
                    continue
                result[filepath] = (mtime, "file")
    return result


def scan_mweb_notes_for_index() -> dict[str, tuple[float, str]]:
    """扫描 MWeb 导出目录，返回笔记路径到 mtime/source_type 的映射。

    Returns:
        dict[str, tuple[float, str]]: `{filepath: (mtime, "mweb")}` 映射。

    Core logic:
        仅在启用 MWeb 且导出目录存在时扫描 `.md` 文件；不读取正文。
    """
    settings = get_settings()
    result: dict[str, tuple[float, str]] = {}
    if not settings.enable_mweb:
        return result
    mweb_dir = settings.mweb_dir
    if not mweb_dir or not os.path.isdir(mweb_dir):
        return result
    for root, dirs, files in os.walk(mweb_dir):
        dirs[:] = [dirname for dirname in dirs if not dirname.startswith(".")]
        for filename in files:
            if filename.startswith(".") or not filename.endswith(".md"):
                continue
            filepath = normalize_path(os.path.join(root, filename))
            try:
                mtime = os.path.getmtime(filepath)
            except OSError:
                continue
            result[filepath] = (mtime, "mweb")
    return result
