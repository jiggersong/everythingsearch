"""查询规划模块。"""

from __future__ import annotations

import re
from typing import Protocol

import jieba

from everythingsearch.request_validation import SearchRequest
from everythingsearch.retrieval.models import QueryPlan


class QueryPlanner(Protocol):
    """查询规划器协议。"""

    def plan(self, request: SearchRequest) -> QueryPlan:
        """将用户请求转换为检索计划。"""


class DefaultQueryPlanner:
    """默认的查询规划器实现。"""

    def plan(self, request: SearchRequest) -> QueryPlan:
        raw_query = request.query.strip()
        
        # 判断查询类型（启发式规则，第一版先简单实现）
        query_type = self._determine_query_type(raw_query)
        exactness_level = "medium"
        
        # 强制精确匹配标志
        if request.exact_focus or request.filename_only:
            exactness_level = "high"
            
        # 预分词处理，以便生成适合 FTS 检索的 query
        sparse_query = self._build_sparse_query(raw_query, getattr(request, "filename_only", False))
        
        # 暂时直接透传 dense_query，后续可以进行扩写或清洗
        dense_query = raw_query

        # 设置召回数（设计文档 §7.2 默认规则）
        if query_type == "exact":
            sparse_top_k, dense_top_k, fusion_top_k, rerank_top_k = 150, 30, 80, 40
        elif query_type == "semantic":
            sparse_top_k, dense_top_k, fusion_top_k, rerank_top_k = 80, 150, 100, 50
        elif query_type == "filename":
            sparse_top_k, dense_top_k, fusion_top_k, rerank_top_k = 200, 20, 80, 40
        elif query_type == "code":
            sparse_top_k, dense_top_k, fusion_top_k, rerank_top_k = 180, 80, 100, 50
        else:
            sparse_top_k, dense_top_k, fusion_top_k, rerank_top_k = 120, 120, 100, 50

        # 如果原 SearchRequest 有明确的 limit 限制，保证 top_k 足量
        # 第一阶段先用 limit，后续将把 topK 逻辑分层。
        if request.limit:
            rerank_top_k = max(rerank_top_k, request.limit)
            fusion_top_k = max(fusion_top_k, rerank_top_k * 2)

        return QueryPlan(
            raw_query=raw_query,
            normalized_query=raw_query.lower(),
            sparse_query=sparse_query,
            dense_query=dense_query,
            query_type=query_type,
            exactness_level=exactness_level,
            source_filter=request.source if request.source != "all" else None,
            date_field=request.date_field or "mtime",
            date_from=request.date_from,
            date_to=request.date_to,
            sparse_top_k=sparse_top_k,
            dense_top_k=dense_top_k,
            fusion_top_k=fusion_top_k,
            rerank_top_k=rerank_top_k,
            path_filter=request.path_filter,
            filename_only=getattr(request, "filename_only", False),
        )

    def _determine_query_type(self, query: str) -> str:
        """根据规则判断查询类型。"""
        # 包含引号强制认为 exact
        if '"' in query or "'" in query:
            return "exact"
        # 包含后缀名
        if re.search(r'\.[a-zA-Z0-9]{1,4}$', query):
            return "filename"
        # 包含常见代码特征
        if re.search(r'(def |class |import |Exception|Error|\.py)', query):
            return "code"
        # 长文本认为是语义搜索
        if len(query) > 15 and len(query.split()) > 4:
            return "semantic"
        return "hybrid"

    def _build_sparse_query(self, query: str, filename_only: bool = False) -> str:
        """生成稀疏查询字符串。"""
        if not query:
            return ""
        
        # 去除现有的双引号，避免解析错误
        query = query.replace('"', ' ')
        
        # 将输入分词后连接
        tokens = list(jieba.cut_for_search(query))
        if not tokens:
            return ""
        
        safe_tokens = []
        for t in tokens:
            t = t.strip()
            if not t:
                continue
            # 使用双引号包裹每个 token，防止特殊字符（如 ., #, - 等）触发 FTS5 语法错误
            safe_tokens.append(f'"{t}"')
            
        joined_query = " ".join(safe_tokens)
        if filename_only:
            return f"{{filename}} : {joined_query}"
        return joined_query
