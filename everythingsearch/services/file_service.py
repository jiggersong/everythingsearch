"""文件相关业务服务。"""

from __future__ import annotations

from dataclasses import dataclass
import mimetypes
import os
import subprocess

from ..file_access import resolve_authorized_file
from ..infra.settings import get_settings
from ..request_validation import FileBodyRequest, FileQueryRequest


class BinaryPreviewNotAllowedError(Exception):
    """文件为二进制内容，不允许文本预览。"""

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        super().__init__(f"二进制文件不可预览: {filepath}")


@dataclass(frozen=True)
class FileReadResult:
    """文件预览结果。"""

    filepath: str
    size: int
    truncated: bool
    content: str


@dataclass(frozen=True)
class FileDownloadResult:
    """文件下载准备结果。"""

    resolved_path: str
    download_name: str
    mimetype: str


@dataclass(frozen=True)
class FileActionResult:
    """文件动作执行结果。"""

    ok: bool = True


class FileService:
    """文件业务服务。"""

    def read_file_preview(self, req: FileQueryRequest) -> FileReadResult:
        """读取文件文本预览。"""
        resolved_path = resolve_authorized_file(req.filepath)
        max_bytes = self._resolve_max_bytes(req.max_bytes)

        with open(resolved_path, "rb") as file_obj:
            raw = file_obj.read(max_bytes + 1)

        truncated = len(raw) > max_bytes
        raw = raw[:max_bytes]
        if b"\x00" in raw[:8192]:
            raise BinaryPreviewNotAllowedError(resolved_path)

        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("utf-8", errors="replace")

        stat_result = os.stat(resolved_path)
        return FileReadResult(
            filepath=resolved_path,
            size=stat_result.st_size,
            truncated=truncated,
            content=content,
        )

    def prepare_file_download(self, req: FileQueryRequest) -> FileDownloadResult:
        """准备文件下载所需元数据。"""
        resolved_path = resolve_authorized_file(req.filepath)
        download_name = os.path.basename(resolved_path)
        guessed_type, _ = mimetypes.guess_type(download_name)
        return FileDownloadResult(
            resolved_path=resolved_path,
            download_name=download_name,
            mimetype=guessed_type or "application/octet-stream",
        )

    def open_file(self, req: FileBodyRequest) -> FileActionResult:
        """使用系统默认应用打开文件。"""
        resolved_path = resolve_authorized_file(req.filepath)
        subprocess.Popen(["open", resolved_path])
        return FileActionResult()

    def reveal_file(self, req: FileBodyRequest) -> FileActionResult:
        """在 Finder 中定位文件。"""
        resolved_path = resolve_authorized_file(req.filepath)
        subprocess.Popen(["open", "-R", resolved_path])
        return FileActionResult()

    @staticmethod
    def _resolve_max_bytes(max_bytes: int | None) -> int:
        """计算允许读取的最大字节数。"""
        cap = get_settings().api_max_read_bytes
        if max_bytes is None:
            return cap
        return min(max_bytes, cap)
