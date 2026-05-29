"""chunk 转换共享逻辑测试。"""

from __future__ import annotations

from langchain_core.documents import Document

from everythingsearch.indexing.chunk_conversion import compact_title_path, docs_to_indexed_chunks


def test_compact_title_path_limits_depth_and_total_chars():
    """title_path 应限制深度和总长度。"""
    long_title = "a" * 200
    title_path = (" 一级目录 ", "二级目录", long_title, "四级目录")

    compacted = compact_title_path(title_path)

    assert len(compacted) == 3
    assert compacted[0] == "一级目录"
    assert compacted[1] == "二级目录"
    assert len(compacted[2]) == 120
    assert sum(len(item) for item in compacted) <= 256


def test_docs_to_indexed_chunks_generates_stable_ids_and_compacts_title_path():
    """共享转换函数应统一 chunk_id 规则并压缩 title_path。"""
    docs = [
        Document(
            page_content="文件名块",
            metadata={
                "chunk_type": "filename",
                "filename": "note.md",
                "type": "md",
                "title_path": ["A", "B", "C", "D"],
                "mtime": 10.0,
                "ctime": 9.0,
                "source": "/tmp/note.md",
            },
        ),
        Document(
            page_content="标题块",
            metadata={
                "chunk_type": "heading",
                "filename": "note.md",
                "type": "md",
                "title_path": ["A", "B", "C", "D"],
                "mtime": 10.0,
                "ctime": 9.0,
                "source": "/tmp/note.md",
            },
        ),
        Document(
            page_content="内容块",
            metadata={
                "chunk_type": "content",
                "chunk_idx": 3,
                "filename": "note.md",
                "type": "md",
                "title_path": ["A", "B", "C", "D"],
                "mtime": 10.0,
                "ctime": 9.0,
                "source": "/tmp/note.md",
            },
        ),
    ]

    chunks = docs_to_indexed_chunks("/tmp/note.md", "file", docs)

    assert [chunk.chunk_id.split("_")[-1] for chunk in chunks] == ["fn", "h0", "c3"]
    assert chunks[0].title_path == ("A", "B", "C")
    assert chunks[1].title_path == ("A", "B", "C")
    assert chunks[2].title_path == ("A", "B", "C")
