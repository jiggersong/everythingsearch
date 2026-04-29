"""轻量索引文件扫描测试。"""

from __future__ import annotations

from types import SimpleNamespace

from everythingsearch.indexing import file_scanner


class TestIndexingFileScanner:
    """测试不读取正文的索引盘点能力。"""

    def test_scan_disk_files_filters_supported_extensions(self, monkeypatch, tmp_path):
        """普通目录扫描应只返回受支持且非隐藏的文件。"""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "a.md").write_text("a", encoding="utf-8")
        (docs_dir / "b.tmp").write_text("b", encoding="utf-8")
        (docs_dir / ".hidden.md").write_text("hidden", encoding="utf-8")

        settings = SimpleNamespace(
            target_dirs=(str(docs_dir),),
            supported_extensions=frozenset({".md"}),
            index_only_keywords=(),
        )
        monkeypatch.setattr(file_scanner, "get_settings", lambda: settings)
        monkeypatch.setattr(file_scanner, "require_target_dirs", lambda _settings: settings.target_dirs)

        result = file_scanner.scan_disk_files_for_index()

        assert list(result.keys()) == [str(docs_dir / "a.md")]
        assert list(result.values())[0][1] == "file"

    def test_scan_mweb_notes_respects_enable_flag(self, monkeypatch, tmp_path):
        """MWeb 未启用时不扫描目录。"""
        mweb_dir = tmp_path / "mweb"
        mweb_dir.mkdir()
        (mweb_dir / "note.md").write_text("note", encoding="utf-8")
        settings = SimpleNamespace(enable_mweb=False, mweb_dir=str(mweb_dir))
        monkeypatch.setattr(file_scanner, "get_settings", lambda: settings)

        assert file_scanner.scan_mweb_notes_for_index() == {}

    def test_scan_mweb_notes_returns_markdown_files(self, monkeypatch, tmp_path):
        """MWeb 扫描应只返回 Markdown 笔记。"""
        mweb_dir = tmp_path / "mweb"
        mweb_dir.mkdir()
        (mweb_dir / "note.md").write_text("note", encoding="utf-8")
        (mweb_dir / "asset.png").write_text("asset", encoding="utf-8")
        settings = SimpleNamespace(enable_mweb=True, mweb_dir=str(mweb_dir))
        monkeypatch.setattr(file_scanner, "get_settings", lambda: settings)

        result = file_scanner.scan_mweb_notes_for_index()

        assert list(result.keys()) == [str(mweb_dir / "note.md")]
        assert list(result.values())[0][1] == "mweb"
