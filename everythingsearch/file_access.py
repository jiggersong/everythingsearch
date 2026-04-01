"""文件访问授权辅助逻辑。"""

from __future__ import annotations

import os

from .infra.settings import get_settings


class FileAuthorizationError(Exception):
    """文件授权相关错误基类。"""


class InvalidPathError(FileAuthorizationError):
    """输入路径为空或格式非法。"""


class TargetFileNotFoundError(FileAuthorizationError):
    """目标文件不存在，或目标不是普通文件。"""


class UnauthorizedFileError(FileAuthorizationError):
    """目标文件存在，但不在授权根目录内。"""


def get_authorized_roots() -> list[str]:
    """返回所有已授权的索引根目录（canonical realpath）。"""
    roots: list[str] = []
    settings = get_settings()
    raw_roots = list(settings.target_dirs)

    for raw_root in raw_roots:
        _append_authorized_root(roots, raw_root)

    if settings.enable_mweb:
        _append_authorized_root(roots, settings.mweb_dir or "")

    return roots


def resolve_authorized_file(raw_path: str) -> str:
    """将用户输入路径解析为可安全使用的 canonical 文件路径。"""
    if not raw_path or not str(raw_path).strip():
        raise InvalidPathError("路径不能为空")

    normalized_parts = os.path.normpath(str(raw_path)).split(os.sep)
    if ".." in normalized_parts:
        raise InvalidPathError("路径包含非法父级跳转")

    try:
        resolved_path = os.path.abspath(os.path.realpath(str(raw_path)))
    except OSError as exc:
        raise InvalidPathError(f"路径解析失败: {exc}") from exc

    try:
        if not os.path.exists(resolved_path):
            raise TargetFileNotFoundError("目标文件不存在")
        if not os.path.isfile(resolved_path):
            raise TargetFileNotFoundError("目标不是普通文件")
    except OSError as exc:
        raise InvalidPathError(f"文件状态检查失败: {exc}") from exc

    for root in get_authorized_roots():
        if resolved_path == root or resolved_path.startswith(root + os.sep):
            return resolved_path

    raise UnauthorizedFileError("目标文件不在授权根目录内")


def is_authorized_file(raw_path: str) -> bool:
    """布尔封装：文件是否在授权范围内。"""
    try:
        resolve_authorized_file(raw_path)
        return True
    except FileAuthorizationError:
        return False


def _append_authorized_root(roots: list[str], raw_root: str) -> None:
    """向授权根目录列表追加规范化后的目录，并尽量去重。"""
    if not raw_root:
        return
    try:
        resolved_root = os.path.abspath(os.path.realpath(str(raw_root)))
    except OSError:
        return
    if not os.path.isdir(resolved_root):
        return
    if resolved_root not in roots:
        roots.append(resolved_root)
