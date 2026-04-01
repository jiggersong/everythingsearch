"""路径发现与归一化工具。"""

from __future__ import annotations

from pathlib import Path


def get_project_root() -> Path:
    """返回仓库根目录。"""
    return Path(__file__).resolve().parents[2]
