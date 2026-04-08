"""搜索相关业务服务。"""

from __future__ import annotations

from dataclasses import dataclass

from ..infra.settings import get_settings
from ..request_validation import SearchRequest
from ..search import (
    SearchExecutionBusyError,
    SearchTimeoutError,
    clear_search_cache,
    get_search_cache_max_size,
    get_search_cache_size,
    search_core,
)


class SearchSourceNotAvailableError(Exception):
    """当前实例未启用指定搜索数据源。"""


class SearchExecutionTimeoutError(Exception):
    """搜索执行超时。"""


class SearchExecutionBusyServiceError(Exception):
    """搜索执行器繁忙。"""


@dataclass(frozen=True)
class SearchExecutionResult:
    """搜索执行结果。"""

    query: str
    results: list[dict]


@dataclass(frozen=True)
class SearchCacheStats:
    """搜索缓存统计信息。"""

    cached_queries: int
    max_cache_size: int


@dataclass(frozen=True)
class SearchCacheClearResult:
    """搜索缓存清理结果。"""

    ok: bool = True
    message: str = "搜索缓存已清空"


class SearchService:
    """搜索业务服务。"""

    def search(self, req: SearchRequest) -> SearchExecutionResult:
        """执行搜索请求。"""
        query = req.query
        source = req.source

        if not query:
            return SearchExecutionResult(query="", results=[])

        enable_mweb = get_settings().enable_mweb
        if not enable_mweb and source == "mweb":
            raise SearchSourceNotAvailableError(
                "当前实例已关闭 MWeb 数据源（ENABLE_MWEB=False）"
            )
        if not enable_mweb and source == "all":
            source = "file"

        try:
            results = search_core(
                query,
                source_filter=source,
                date_field=req.date_field,
                date_from=req.date_from,
                date_to=req.date_to,
                exact_focus=req.exact_focus,
            )
        except SearchTimeoutError as exc:
            raise SearchExecutionTimeoutError(str(exc)) from exc
        except SearchExecutionBusyError as exc:
            raise SearchExecutionBusyServiceError(str(exc)) from exc
        if req.limit is not None:
            results = results[:req.limit]

        return SearchExecutionResult(query=query, results=results)

    def clear_cache(self) -> SearchCacheClearResult:
        """清空搜索缓存。"""
        clear_search_cache()
        return SearchCacheClearResult()

    def get_cache_stats(self) -> SearchCacheStats:
        """获取搜索缓存统计信息。"""
        return SearchCacheStats(
            cached_queries=get_search_cache_size(),
            max_cache_size=get_search_cache_max_size(),
        )
