"""路径与文本规范化工具。"""

from __future__ import annotations

import re
import unicodedata

_LONE_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def normalize_path(path_str: str) -> str:
    """将 macOS 常见的 NFD 编码强制转为 NFC 标准编码。"""
    return unicodedata.normalize("NFC", path_str)


def strip_lone_surrogates(text: str) -> str:
    """剥离孤立的 UTF-16 代理项字符，避免 UTF-8 编码崩溃。"""
    if not text:
        return text
    return _LONE_SURROGATE_RE.sub("", text)
