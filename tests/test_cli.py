"""CLI 搜索输出单元测试。"""

from everythingsearch.cli import _extract_snippet


class TestExtractSnippet:
    def test_prefers_snippet_when_present(self):
        doc = {"snippet": "from snippet", "preview": "from preview"}
        assert _extract_snippet(doc, doc) == "from snippet"

    def test_falls_back_to_preview(self):
        doc = {"preview": "hit preview", "content": "full content"}
        assert _extract_snippet(doc, doc) == "hit preview"

    def test_falls_back_to_content(self):
        doc = {"content": "body text"}
        assert _extract_snippet(doc, doc) == "body text"

    def test_empty_when_no_text_fields(self):
        assert _extract_snippet({"filepath": "/a.txt"}, {"filepath": "/a.txt"}) == ""
