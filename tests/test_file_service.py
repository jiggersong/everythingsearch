"""测试文件服务层。"""

from __future__ import annotations

import os

import pytest

import config
from everythingsearch.infra.settings import reset_settings_cache
from everythingsearch.request_validation import FileBodyRequest, FileQueryRequest
from everythingsearch.services.file_service import (
    BinaryPreviewNotAllowedError,
    FileActionResult,
    FileDownloadResult,
    FileReadResult,
    FileService,
)


@pytest.fixture
def file_service_workspace(tmp_path, monkeypatch):
    """创建 FileService 测试工作区。"""
    indexed_root = tmp_path / "indexed"
    indexed_root.mkdir()

    monkeypatch.setattr(config, "TARGET_DIR", [str(indexed_root)])
    monkeypatch.setattr(config, "ENABLE_MWEB", False, raising=False)
    monkeypatch.setattr(config, "MWEB_DIR", "", raising=False)
    monkeypatch.setattr(config, "API_MAX_READ_BYTES", 16, raising=False)
    reset_settings_cache()

    try:
        yield indexed_root
    finally:
        reset_settings_cache()


class TestFileService:
    """测试文件服务。"""

    def test_read_file_preview_success(self, file_service_workspace):
        target = file_service_workspace / "note.txt"
        target.write_text("hello world", encoding="utf-8")

        result = FileService().read_file_preview(
            FileQueryRequest(filepath=str(target), max_bytes=None)
        )

        assert result == FileReadResult(
            filepath=str(target.resolve()),
            size=11,
            truncated=False,
            content="hello world",
        )

    def test_read_file_preview_uses_cap(self, file_service_workspace):
        target = file_service_workspace / "note.txt"
        target.write_text("0123456789ABCDEFG", encoding="utf-8")

        result = FileService().read_file_preview(
            FileQueryRequest(filepath=str(target), max_bytes=None)
        )

        assert result.truncated is True
        assert result.content == "0123456789ABCDEF"

    def test_read_file_preview_respects_explicit_max_bytes(self, file_service_workspace):
        target = file_service_workspace / "note.txt"
        target.write_text("0123456789ABCDEFG", encoding="utf-8")

        result = FileService().read_file_preview(
            FileQueryRequest(filepath=str(target), max_bytes=8)
        )

        assert result.truncated is True
        assert result.content == "01234567"

    def test_read_file_preview_rejects_binary(self, file_service_workspace):
        target = file_service_workspace / "data.bin"
        target.write_bytes(b"abc\x00def")

        with pytest.raises(BinaryPreviewNotAllowedError) as exc_info:
            FileService().read_file_preview(
                FileQueryRequest(filepath=str(target), max_bytes=None)
            )

        assert exc_info.value.filepath == str(target.resolve())

    def test_prepare_file_download_returns_metadata(self, file_service_workspace):
        target = file_service_workspace / "report.txt"
        target.write_text("download", encoding="utf-8")

        result = FileService().prepare_file_download(
            FileQueryRequest(filepath=str(target), max_bytes=None)
        )

        assert result == FileDownloadResult(
            resolved_path=str(target.resolve()),
            download_name="report.txt",
            mimetype="text/plain",
        )

    def test_open_file_uses_resolved_path(self, file_service_workspace, monkeypatch):
        target = file_service_workspace / "note.txt"
        target.write_text("open", encoding="utf-8")
        called = {}

        def fake_popen(args):
            called["args"] = args
            class DummyProcess:
                pass
            return DummyProcess()

        monkeypatch.setattr("everythingsearch.services.file_service.subprocess.Popen", fake_popen)

        result = FileService().open_file(FileBodyRequest(filepath=str(target)))

        assert result == FileActionResult()
        assert called["args"] == ["open", str(target.resolve())]

    def test_reveal_file_uses_resolved_path(self, file_service_workspace, monkeypatch):
        target = file_service_workspace / "note.txt"
        target.write_text("reveal", encoding="utf-8")
        called = {}

        def fake_popen(args):
            called["args"] = args
            class DummyProcess:
                pass
            return DummyProcess()

        monkeypatch.setattr("everythingsearch.services.file_service.subprocess.Popen", fake_popen)

        result = FileService().reveal_file(FileBodyRequest(filepath=str(target)))

        assert result == FileActionResult()
        assert called["args"] == ["open", "-R", str(target.resolve())]
