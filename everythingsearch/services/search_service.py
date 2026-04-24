"""搜索相关业务服务。"""

from __future__ import annotations

from dataclasses import dataclass

from ..infra.settings import get_settings
from ..request_validation import SearchRequest


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


class SearchService:
    """搜索业务服务。"""

    def __init__(self):
        from everythingsearch.retrieval.pipeline import SearchPipeline
        self._pipeline = SearchPipeline()

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

        # 映射旧版的 source 参数
        if source == "all":
            source_filter = None
        else:
            source_filter = source

        from everythingsearch.request_validation import SearchRequest as PipelineSearchRequest
        # 构建 Pipeline 可接受的 Request 对象
        pipeline_req = PipelineSearchRequest(
            query=query,
            source=source_filter or "all",
            date_field=req.date_field,
            date_from=req.date_from,
            date_to=req.date_to,
            limit=req.limit,
            exact_focus=req.exact_focus,
            path_filter=req.path_filter,
            filename_only=req.filename_only,
        )

        try:
            results = self._pipeline.search(pipeline_req)
        except Exception as exc:
            # 捕获可能的底层异常映射为 503 兼容前端
            raise SearchExecutionBusyServiceError(str(exc)) from exc

        return SearchExecutionResult(query=query, results=results)
