"""测试文件访问授权辅助逻辑。"""

from __future__ import annotations

import os

import pytest

import config
from everythingsearch.infra.settings import reset_settings_cache
from everythingsearch.file_access import (
    InvalidPathError,
    TargetFileNotFoundError,
    UnauthorizedFileError,
    get_authorized_roots,
    is_authorized_file,
    resolve_authorized_file,
)


@pytest.fixture
def indexed_workspace(tmp_path, monkeypatch):
    """创建带索引根目录的测试工作区。"""
    root = tmp_path / "root"
    root.mkdir()

    nested_root = root / "nested"
    nested_root.mkdir()

    outside = tmp_path / "outside"
    outside.mkdir()

    monkeypatch.setattr(config, "TARGET_DIR", [str(root), str(nested_root)])
    monkeypatch.setattr(config, "ENABLE_MWEB", False, raising=False)
    monkeypatch.setattr(config, "MWEB_DIR", "", raising=False)
    reset_settings_cache()

    try:
        yield {
            "root": root,
            "nested_root": nested_root,
            "outside": outside,
        }
    finally:
        reset_settings_cache()


class TestGetAuthorizedRoots:
    """测试授权根目录解析。"""

    def test_overlapping_roots_are_kept_canonical(self, indexed_workspace):
        roots = get_authorized_roots()
        assert str(indexed_workspace["root"].resolve()) in roots
        assert str(indexed_workspace["nested_root"].resolve()) in roots


class TestResolveAuthorizedFile:
    """测试授权文件路径解析。"""

    def test_resolve_authorized_file_returns_realpath(self, indexed_workspace):
        target = indexed_workspace["root"] / "note.txt"
        target.write_text("hello", encoding="utf-8")

        resolved = resolve_authorized_file(str(target))

        assert resolved == str(target.resolve())

    def test_empty_path_raises_invalid_path(self):
        with pytest.raises(InvalidPathError):
            resolve_authorized_file("")

    def test_parent_traversal_raises_invalid_path(self):
        with pytest.raises(InvalidPathError):
            resolve_authorized_file("../tmp/test.txt")

    def test_nonexistent_target_raises_not_found(self, indexed_workspace):
        with pytest.raises(TargetFileNotFoundError):
            resolve_authorized_file(str(indexed_workspace["root"] / "missing.txt"))

    def test_directory_target_raises_not_found(self, indexed_workspace):
        with pytest.raises(TargetFileNotFoundError):
            resolve_authorized_file(str(indexed_workspace["root"]))

    def test_existing_file_outside_roots_raises_unauthorized(self, indexed_workspace):
        target = indexed_workspace["outside"] / "secret.txt"
        target.write_text("secret", encoding="utf-8")

        with pytest.raises(UnauthorizedFileError):
            resolve_authorized_file(str(target))

    def test_symlink_escape_raises_unauthorized(self, indexed_workspace):
        outside_target = indexed_workspace["outside"] / "secret.txt"
        outside_target.write_text("secret", encoding="utf-8")

        symlink_path = indexed_workspace["root"] / "escape.txt"
        os.symlink(outside_target, symlink_path)

        with pytest.raises(UnauthorizedFileError):
            resolve_authorized_file(str(symlink_path))


class TestIsAuthorizedFile:
    """测试布尔封装接口。"""

    def test_returns_true_for_indexed_file(self, indexed_workspace):
        target = indexed_workspace["root"] / "note.txt"
        target.write_text("hello", encoding="utf-8")

        assert is_authorized_file(str(target)) is True

    def test_returns_false_for_outside_file(self, indexed_workspace):
        target = indexed_workspace["outside"] / "secret.txt"
        target.write_text("secret", encoding="utf-8")

        assert is_authorized_file(str(target)) is False
