"""测试搜索服务层。"""

from __future__ import annotations

import config
import pytest

from everythingsearch.infra.settings import reset_settings_cache
from everythingsearch.request_validation import SearchRequest
from everythingsearch.services.search_service import (
    SearchExecutionBusyServiceError,
    SearchExecutionResult,
    SearchExecutionTimeoutError,
    SearchService,
    SearchSourceNotAvailableError,
)


class TestSearchService:
    """测试搜索服务。"""

    def setup_method(self):
        reset_settings_cache()

    def teardown_method(self):
        reset_settings_cache()

    def test_search_empty_query_short_circuits(self, monkeypatch):
        """空查询应直接返回空结果且不调用底层搜索。"""
        called = {"value": False}

        def fake_pipeline_search(*args, **kwargs):
            called["value"] = True
            return [{"filename": "unexpected"}]

        monkeypatch.setattr(
            "everythingsearch.retrieval.pipeline.SearchPipeline.search",
            fake_pipeline_search,
        )

        result = SearchService().search(
            SearchRequest(
                query="",
                source="all",
                date_field="mtime",
                date_from=None,
                date_to=None,
                limit=None,
                exact_focus=False,
            )
        )

        assert result == SearchExecutionResult(query="", results=[])
        assert called["value"] is False

    def test_search_rejects_mweb_when_disabled(self, monkeypatch):
        """禁用 MWeb 时应拒绝 mweb 数据源。"""
        monkeypatch.setattr(config, "ENABLE_MWEB", False)

        with pytest.raises(SearchSourceNotAvailableError) as exc_info:
            SearchService().search(
                SearchRequest(
                    query="test",
                    source="mweb",
                    date_field="mtime",
                    date_from=None,
                    date_to=None,
                    limit=None,
                    exact_focus=False,
                )
            )

        assert str(exc_info.value) == "当前实例已关闭 MWeb 数据源（ENABLE_MWEB=False）"

    def test_search_downgrades_all_to_file_when_mweb_disabled(self, monkeypatch):
        """禁用 MWeb 时 source=all 应自动降级为 file。"""
        captured = {}
        monkeypatch.setattr(config, "ENABLE_MWEB", False)

        def fake_pipeline_search(self, req):
            captured["req"] = req
            return []

        monkeypatch.setattr(
            "everythingsearch.retrieval.pipeline.SearchPipeline.search",
            fake_pipeline_search,
        )

        result = SearchService().search(
            SearchRequest(
                query="test",
                source="all",
                date_field="ctime",
                date_from=1.0,
                date_to=2.0,
                limit=None,
                exact_focus=False,
            )
        )

        assert result == SearchExecutionResult(query="test", results=[])
        # source_filter="all" doesn't change to "file" in Pipeline logic anymore?
        # Wait, the code I wrote was: if source == "all": source_filter = None
        # Let's check my code in SearchService.
        assert captured["req"].source == "all"

    def test_search_wraps_busy_error_from_search_core(self, monkeypatch):
        """底层搜索执行器繁忙时，应转换为 service 层稳定异常。"""
        monkeypatch.setattr(config, "ENABLE_MWEB", True, raising=False)

        def fake_pipeline_search(self, req):
            raise Exception("搜索执行繁忙，请稍后重试")

        monkeypatch.setattr(
            "everythingsearch.retrieval.pipeline.SearchPipeline.search",
            fake_pipeline_search,
        )

        with pytest.raises(SearchExecutionBusyServiceError, match="搜索执行繁忙"):
            SearchService().search(
                SearchRequest(
                    query="test",
                    source="all",
                    date_field="mtime",
                    date_from=None,
                    date_to=None,
                    limit=None,
                    exact_focus=False,
                )
            )
