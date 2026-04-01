"""测试索引构建功能"""
import pytest
import sys
import os
import tempfile
import sqlite3
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from everythingsearch.indexer import (
    normalize_path,
    _extract_md_headings,
    _parse_front_matter,
    _truncate_for_embed,
    _init_scan_cache,
    _load_cached_docs,
    _save_cached_docs,
    _prune_scan_cache,
    build_documents_for_path_cached,
    load_file_content,
    calculate_batch_size,
    build_index,
    EMBED_MAX_CHARS,
)
from langchain_core.documents import Document


class TestNormalizePath:
    """测试路径规范化"""
    
    def test_nfd_to_nfc_conversion(self):
        """测试 NFD 到 NFC 转换"""
        # é 的分解形式 (NFD) vs 组合形式 (NFC)
        nfd_path = "cafe\u0301.txt"
        nfc_path = "caf\u00e9.txt"
        
        result = normalize_path(nfd_path)
        assert result == nfc_path
    
    def test_already_nfc_unchanged(self):
        """测试已经是 NFC 的路径保持不变"""
        path = "/Users/test/file.txt"
        result = normalize_path(path)
        assert result == path
    
    def test_chinese_characters(self):
        """测试中文字符处理"""
        path = "/Users/测试/文件.txt"
        result = normalize_path(path)
        assert result == path  # 中文已经是 NFC


class TestExtractMdHeadings:
    """测试 Markdown 标题提取"""
    
    def test_extract_h1(self):
        """测试提取一级标题"""
        content = "# Title 1\n\nSome content\n# Title 2"
        headings = _extract_md_headings(content)
        assert "Title 1" in headings
        assert "Title 2" in headings
    
    def test_extract_all_levels(self):
        """测试提取各级标题"""
        content = """
# H1
## H2
### H3
#### H4
##### H5
###### H6
####### Not a heading
        """
        headings = _extract_md_headings(content)
        assert "H1" in headings
        assert "H2" in headings
        assert "H3" in headings
        assert "H4" in headings
        assert "H5" in headings
        assert "H6" in headings
        assert "Not a heading" not in headings
    
    def test_no_headings(self):
        """测试无标题内容"""
        content = "Just some plain text\nwithout any headings"
        headings = _extract_md_headings(content)
        assert headings == []
    
    def test_headings_with_extra_spaces(self):
        """测试带额外空格的标题"""
        content = "#    Title with spaces   "
        headings = _extract_md_headings(content)
        # 正则保留尾部空格，这是符合预期的行为
        assert "Title with spaces   " in headings


class TestParseFrontMatter:
    """测试 Front Matter 解析"""
    
    def test_valid_yaml_front_matter(self):
        """测试有效 YAML Front Matter"""
        content = """---
title: Test Title
categories: [cat1, cat2]
tags: tag1, tag2
---

Body content here.
"""
        meta, body = _parse_front_matter(content)
        assert meta["title"] == "Test Title"
        assert meta["categories"] == ["cat1", "cat2"]
        assert "Body content here" in body
    
    def test_no_front_matter(self):
        """测试无 Front Matter"""
        content = "Just regular content\nwithout front matter"
        meta, body = _parse_front_matter(content)
        assert meta == {}
        assert body == content
    
    def test_invalid_yaml(self):
        """测试无效 YAML"""
        content = """---
invalid: yaml: [
---

Body"""
        meta, body = _parse_front_matter(content)
        # 应该返回空 meta，但包含 body
        assert body.strip() == "Body"
    
    def test_incomplete_front_matter(self):
        """测试不完整的 Front Matter"""
        content = "---\nsome: data\n\nNo end marker"
        meta, body = _parse_front_matter(content)
        assert meta == {}  # 没有结束标记，返回空
        assert body == content


class TestTruncateForEmbed:
    """测试文本截断"""
    
    def test_short_text_unchanged(self):
        """测试短文本保持不变"""
        text = "Short text"
        result = _truncate_for_embed(text)
        assert result == text
    
    def test_long_text_truncated(self):
        """测试长文本被截断"""
        text = "x" * (EMBED_MAX_CHARS + 100)
        result = _truncate_for_embed(text)
        assert len(result) == EMBED_MAX_CHARS
    
    def test_empty_text_returns_space(self):
        """测试空文本返回空格"""
        assert _truncate_for_embed("") == " "
        assert _truncate_for_embed("   ") == " "
        assert _truncate_for_embed(None) == " "
    
    def test_exact_max_length(self):
        """测试恰好最大长度"""
        text = "x" * EMBED_MAX_CHARS
        result = _truncate_for_embed(text)
        assert result == text


class TestBuildDocuments:
    """测试文档构建（需要配置）"""
    
    @pytest.mark.skipif(
        not os.path.exists("config.py"),
        reason="需要配置 config.py"
    )
    def test_build_documents_for_txt(self, sample_text_file):
        """测试文本文件文档构建"""
        try:
            from everythingsearch.indexer import build_documents_for_file
            from langchain_core.documents import Document
            
            docs = build_documents_for_file(
                sample_text_file,
                os.path.basename(sample_text_file),
                ".txt"
            )
            
            # 至少应该有文件名文档
            assert len(docs) > 0
            
            # 检查元数据
            assert docs[0].metadata["chunk_type"] == "filename"
            assert docs[0].metadata["type"] == ".txt"
            
        except ImportError as e:
            pytest.skip(f"导入失败: {e}")
    
    @pytest.mark.skipif(
        not os.path.exists("config.py"),
        reason="需要配置 config.py"
    )
    def test_build_documents_for_md(self, sample_md_file):
        """测试 Markdown 文件文档构建"""
        try:
            from everythingsearch.indexer import build_documents_for_file
            
            docs = build_documents_for_file(
                sample_md_file,
                os.path.basename(sample_md_file),
                ".md"
            )
            
            # 应该有文件名、标题和内容
            chunk_types = [d.metadata["chunk_type"] for d in docs]
            assert "filename" in chunk_types
            
        except ImportError as e:
            pytest.skip(f"导入失败: {e}")


class TestBatchSizeCalculation:
    """测试动态 batch size 计算"""

    def test_batch_size_calculation_logic(self):
        """与 indexer.calculate_batch_size 保持一致"""
        from langchain_core.documents import Document

        long_docs = [Document(page_content="x" * 500) for _ in range(10)]
        assert calculate_batch_size(long_docs) == 25

        mid_docs = [Document(page_content="x" * 300) for _ in range(10)]
        assert calculate_batch_size(mid_docs) == 40

        short_docs = [Document(page_content="x" * 100) for _ in range(10)]
        assert calculate_batch_size(short_docs) == 55

        assert calculate_batch_size([]) == 50


class TestScanCache:
    """测试扫描缓存边界与故障降级。"""

    def test_load_cached_docs_returns_none_when_mtime_mismatch(self, tmp_path):
        db_path = tmp_path / "scan_cache.db"
        conn = sqlite3.connect(db_path)
        _init_scan_cache(conn)
        docs = [Document(page_content="hello", metadata={"source": "/tmp/a.txt"})]
        _save_cached_docs(conn, "/tmp/a.txt", 100.0, "file", docs)

        cached = _load_cached_docs(conn, "/tmp/a.txt", 100.5)

        assert cached is None
        conn.close()

    def test_load_cached_docs_returns_none_when_json_is_invalid(self, tmp_path):
        db_path = tmp_path / "scan_cache.db"
        conn = sqlite3.connect(db_path)
        _init_scan_cache(conn)
        conn.execute(
            "INSERT OR REPLACE INTO scan_cache (filepath, mtime, source_type, chunks_json) VALUES (?, ?, ?, ?)",
            ("/tmp/a.txt", 100.0, "file", "{broken json"),
        )
        conn.commit()

        cached = _load_cached_docs(conn, "/tmp/a.txt", 100.0)

        assert cached is None
        conn.close()

    def test_build_documents_for_path_cached_uses_cache_without_rebuilding(self, tmp_path, monkeypatch):
        db_path = tmp_path / "scan_cache.db"
        conn = sqlite3.connect(db_path)
        _init_scan_cache(conn)
        cached_docs = [Document(page_content="cached", metadata={"source": "/tmp/a.txt"})]
        _save_cached_docs(conn, "/tmp/a.txt", 100.0, "file", cached_docs)

        monkeypatch.setattr(
            "everythingsearch.indexer.build_documents_for_file",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应重建文档")),
        )

        docs = build_documents_for_path_cached("/tmp/a.txt", 100.0, "file", conn)

        assert len(docs) == 1
        assert docs[0].page_content == "cached"
        conn.close()

    def test_prune_scan_cache_removes_orphans_only(self, tmp_path):
        db_path = tmp_path / "scan_cache.db"
        conn = sqlite3.connect(db_path)
        _init_scan_cache(conn)
        docs = [Document(page_content="hello", metadata={"source": "/tmp/a.txt"})]
        _save_cached_docs(conn, "/tmp/a.txt", 100.0, "file", docs)
        _save_cached_docs(conn, "/tmp/b.txt", 100.0, "file", docs)

        _prune_scan_cache(conn, {"/tmp/a.txt"})

        rows = conn.execute("SELECT filepath FROM scan_cache ORDER BY filepath").fetchall()
        assert rows == [("/tmp/a.txt",)]
        conn.close()


class TestLoadFileContentFailurePaths:
    """测试文件读取故障与降级路径。"""

    def test_load_file_content_returns_empty_for_invalid_office_zip(self, tmp_path, monkeypatch):
        office_file = tmp_path / "broken.docx"
        office_file.write_bytes(b"not-a-zip")
        settings = SimpleNamespace(
            text_extensions=frozenset({".txt", ".md"}),
            media_extensions=frozenset({".png"}),
            office_extensions=frozenset({".docx", ".xlsx", ".pptx", ".pdf"}),
        )

        monkeypatch.setattr("everythingsearch.indexer.get_settings", lambda: settings)

        content, headings = load_file_content(str(office_file), ".docx")

        assert content == ""
        assert headings == []

    def test_load_file_content_returns_empty_when_subprocess_reader_returns_empty(self, tmp_path, monkeypatch):
        office_file = tmp_path / "demo.pdf"
        office_file.write_bytes(b"%PDF-1.4")
        settings = SimpleNamespace(
            text_extensions=frozenset({".txt", ".md"}),
            media_extensions=frozenset({".png"}),
            office_extensions=frozenset({".docx", ".xlsx", ".pptx", ".pdf"}),
        )

        monkeypatch.setattr("everythingsearch.indexer.get_settings", lambda: settings)
        monkeypatch.setattr("everythingsearch.indexer._read_via_subprocess", lambda filepath, ext: ("", []))

        content, headings = load_file_content(str(office_file), ".pdf")

        assert content == ""
        assert headings == []


class TestBuildIndex:
    """测试全量索引构建边界行为。"""

    def test_build_index_clears_existing_collection_when_scan_result_is_empty(self, monkeypatch, tmp_path):
        settings = SimpleNamespace(
            persist_directory=str(tmp_path / "chroma_db"),
            scan_cache_path="",
            embedding_model="text-embedding-v2",
            embedding_cache_path=str(tmp_path / "embedding_cache.db"),
        )
        deleted = []

        class FakeCollection:
            def __init__(self, name):
                self.name = name

        class FakeClient:
            def __init__(self, path):
                self.path = path

            def list_collections(self):
                return [FakeCollection("local_files")]

            def delete_collection(self, name):
                deleted.append(name)

        monkeypatch.setattr("everythingsearch.indexer.get_settings", lambda: settings)
        monkeypatch.setattr("everythingsearch.indexer.require_target_dirs", lambda _settings: ("/tmp/docs",))
        monkeypatch.setattr("everythingsearch.indexer.require_dashscope_api_key", lambda _settings: "fake-key")
        monkeypatch.setattr("everythingsearch.indexer.apply_sdk_environment", lambda _settings: None)
        monkeypatch.setattr("everythingsearch.indexer.scan_files", lambda: ([], 0.1))
        monkeypatch.setattr("everythingsearch.indexer.scan_mweb_notes", lambda: ([], 0.0))
        monkeypatch.setattr("everythingsearch.indexer._cleanup_orphaned_hnsw_dirs", lambda client: None)
        monkeypatch.setattr("chromadb.PersistentClient", FakeClient)

        build_index()

        assert deleted == ["local_files"]
