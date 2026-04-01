"""测试搜索服务层。"""

from __future__ import annotations

import config
import pytest

from everythingsearch.infra.settings import reset_settings_cache
from everythingsearch.request_validation import SearchRequest
from everythingsearch.services.search_service import (
    SearchCacheClearResult,
    SearchCacheStats,
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

        def fake_search_core(*args, **kwargs):
            called["value"] = True
            return [{"filename": "unexpected"}]

        monkeypatch.setattr(
            "everythingsearch.services.search_service.search_core",
            fake_search_core,
        )

        result = SearchService().search(
            SearchRequest(
                query="",
                source="all",
                date_field="mtime",
                date_from=None,
                date_to=None,
                limit=None,
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
                )
            )

        assert str(exc_info.value) == "当前实例已关闭 MWeb 数据源（ENABLE_MWEB=False）"

    def test_search_downgrades_all_to_file_when_mweb_disabled(self, monkeypatch):
        """禁用 MWeb 时 source=all 应自动降级为 file。"""
        captured = {}
        monkeypatch.setattr(config, "ENABLE_MWEB", False)

        def fake_search_core(query, source_filter=None, date_field=None, date_from=None, date_to=None):
            captured["query"] = query
            captured["source_filter"] = source_filter
            captured["date_field"] = date_field
            captured["date_from"] = date_from
            captured["date_to"] = date_to
            return []

        monkeypatch.setattr(
            "everythingsearch.services.search_service.search_core",
            fake_search_core,
        )

        result = SearchService().search(
            SearchRequest(
                query="test",
                source="all",
                date_field="ctime",
                date_from=1.0,
                date_to=2.0,
                limit=None,
            )
        )

        assert result == SearchExecutionResult(query="test", results=[])
        assert captured == {
            "query": "test",
            "source_filter": "file",
            "date_field": "ctime",
            "date_from": 1.0,
            "date_to": 2.0,
        }

    def test_search_applies_limit(self, monkeypatch):
        """limit 应在 service 层统一截断。"""
        monkeypatch.setattr(config, "ENABLE_MWEB", True, raising=False)

        def fake_search_core(*args, **kwargs):
            return [
                {"filename": "1"},
                {"filename": "2"},
                {"filename": "3"},
            ]

        monkeypatch.setattr(
            "everythingsearch.services.search_service.search_core",
            fake_search_core,
        )

        result = SearchService().search(
            SearchRequest(
                query="test",
                source="all",
                date_field="mtime",
                date_from=None,
                date_to=None,
                limit=2,
            )
        )

        assert result == SearchExecutionResult(
            query="test",
            results=[{"filename": "1"}, {"filename": "2"}],
        )

    def test_search_returns_all_results_when_limit_is_none(self, monkeypatch):
        """limit 为空时应返回全部结果。"""
        monkeypatch.setattr(config, "ENABLE_MWEB", True, raising=False)

        def fake_search_core(*args, **kwargs):
            return [{"filename": str(index)} for index in range(5)]

        monkeypatch.setattr(
            "everythingsearch.services.search_service.search_core",
            fake_search_core,
        )

        result = SearchService().search(
            SearchRequest(
                query="test",
                source="all",
                date_field="mtime",
                date_from=None,
                date_to=None,
                limit=None,
            )
        )

        assert result == SearchExecutionResult(
            query="test",
            results=[{"filename": str(index)} for index in range(5)],
        )

    def test_search_wraps_timeout_error_from_search_core(self, monkeypatch):
        """底层搜索超时时，应转换为 service 层稳定异常。"""
        monkeypatch.setattr(config, "ENABLE_MWEB", True, raising=False)

        def fake_search_core(*args, **kwargs):
            from everythingsearch.search import SearchTimeoutError

            raise SearchTimeoutError("搜索操作超时（>30s）")

        monkeypatch.setattr(
            "everythingsearch.services.search_service.search_core",
            fake_search_core,
        )

        with pytest.raises(SearchExecutionTimeoutError, match="搜索操作超时"):
            SearchService().search(
                SearchRequest(
                    query="test",
                    source="all",
                    date_field="mtime",
                    date_from=None,
                    date_to=None,
                    limit=None,
                )
            )

    def test_search_wraps_busy_error_from_search_core(self, monkeypatch):
        """底层搜索执行器繁忙时，应转换为 service 层稳定异常。"""
        monkeypatch.setattr(config, "ENABLE_MWEB", True, raising=False)

        def fake_search_core(*args, **kwargs):
            from everythingsearch.search import SearchExecutionBusyError

            raise SearchExecutionBusyError("搜索执行繁忙，请稍后重试")

        monkeypatch.setattr(
            "everythingsearch.services.search_service.search_core",
            fake_search_core,
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
                )
            )

    def test_clear_cache_calls_backend(self, monkeypatch):
        """清理缓存应调用底层函数。"""
        called = {"value": False}

        def fake_clear_search_cache():
            called["value"] = True

        monkeypatch.setattr(
            "everythingsearch.services.search_service.clear_search_cache",
            fake_clear_search_cache,
        )

        result = SearchService().clear_cache()

        assert result == SearchCacheClearResult()
        assert called["value"] is True

    def test_get_cache_stats_uses_backend_helpers(self, monkeypatch):
        """缓存统计应通过稳定辅助函数获取。"""
        monkeypatch.setattr(
            "everythingsearch.services.search_service.get_search_cache_size",
            lambda: 3,
        )
        monkeypatch.setattr(
            "everythingsearch.services.search_service.get_search_cache_max_size",
            lambda: 100,
        )

        result = SearchService().get_cache_stats()

        assert result == SearchCacheStats(cached_queries=3, max_cache_size=100)
