"""稀疏检索模块。"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Protocol

from everythingsearch.infra.settings import Settings
from everythingsearch.retrieval.models import QueryPlan, SearchCandidate

logger = logging.getLogger(__name__)


class SparseRetriever(Protocol):
    """稀疏检索器协议。"""

    def retrieve(self, plan: QueryPlan) -> list[SearchCandidate]:
        """执行稀疏检索并返回候选。"""


class SQLiteSparseRetriever:
    """基于 SQLite FTS5 的稀疏检索器。"""

    def __init__(self, settings: Settings) -> None:
        self._db_path = settings.sparse_index_path
        self._filename_weight = settings.sparse_filename_weight
        self._path_weight = settings.sparse_path_weight
        self._heading_weight = settings.sparse_heading_weight
        self._content_weight = settings.sparse_content_weight

    def _get_connection(self) -> sqlite3.Connection:
        """获取只读数据库连接。"""
        # URI 模式打开以只读方式
        uri = f"file:{self._db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=5.0, check_same_thread=False)

    def retrieve(self, plan: QueryPlan) -> list[SearchCandidate]:
        if not plan.sparse_query.strip():
            return []

        try:
            import contextlib
            with contextlib.closing(self._get_connection()) as conn:
                with conn:
                    cursor = conn.cursor()
                
                # FTS5 的 BM25 公式： bm25(fts_table, weight_col1, weight_col2...)
                # 我们的列： filename, path_text, heading_text, content_text
                # weight 对应我们在 settings 中的配置。
                
                # FTS5 的 bm25 函数分数越小代表越相关。但为了后续 RRF 融合统一“分数越大越相关”，
                # 我们可以取其负值或原样排序并在返回时转换，这里我们在 SQL 中就 ORDER BY bm25_score (升序)。
                
                query_sql = f"""
                    SELECT 
                        c.chunk_id, c.file_id, c.filepath, c.filename, 
                        c.source_type, c.filetype, c.chunk_type, 
                        c.title_path, c.content, c.metadata_json,
                        bm25(sparse_chunks_fts, ?, ?, ?, ?) AS bm25_score
                    FROM sparse_chunks_fts f
                    JOIN sparse_chunks c ON c.chunk_id = f.chunk_id
                    WHERE sparse_chunks_fts MATCH ?
                """
                
                # 过滤条件
                params: list[str | int | float] = [
                    self._filename_weight,
                    self._path_weight,
                    self._heading_weight,
                    self._content_weight,
                    plan.sparse_query
                ]
                
                if plan.source_filter:
                    query_sql += " AND c.source_type = ?"
                    params.append(plan.source_filter)
                    
                if plan.date_from is not None:
                    query_sql += f" AND c.{plan.date_field} >= ?"
                    params.append(plan.date_from)
                    
                if plan.date_to is not None:
                    query_sql += f" AND c.{plan.date_field} <= ?"
                    params.append(plan.date_to)
                
                if plan.path_filter:
                    query_sql += " AND c.filepath LIKE ?"
                    params.append(f"%{plan.path_filter}%")
                
                # 按分数升序（bm25 越小越好），由于要符合 "score越大越好"，后续会转换
                query_sql += " ORDER BY bm25_score ASC LIMIT ?"
                params.append(plan.sparse_top_k)
                
                cursor.execute(query_sql, tuple(params))
                rows = cursor.fetchall()

                candidates = []
                for rank, row in enumerate(rows, start=1):
                    (chunk_id, file_id, filepath, filename, source_type, filetype, 
                     chunk_type, title_path_json, content, metadata_json, bm25_score) = row
                    
                    try:
                        title_path = tuple(json.loads(title_path_json))
                        metadata = json.loads(metadata_json)
                    except (TypeError, ValueError):
                        title_path = ()
                        metadata = {}

                    # 将 bm25 分数转换为越大越好。可以简单地用一个常数减去，或者取反。
                    # 由于 RRF 融合其实主要依赖 rank，绝对分数不那么重要，但为了调试直观，这里直接取负。
                    sparse_score_normalized = -bm25_score if bm25_score is not None else 0.0

                    candidates.append(SearchCandidate(
                        chunk_id=chunk_id,
                        file_id=file_id,
                        filepath=filepath,
                        filename=filename,
                        chunk_type=chunk_type,
                        content=content,
                        title_path=title_path,
                        source_type=source_type,
                        filetype=filetype,
                        sparse_rank=rank,
                        dense_rank=None,
                        sparse_score=sparse_score_normalized,
                        dense_score=None,
                        fusion_score=0.0,  # 留给 fusion 层
                        metadata=metadata
                    ))
                
                return candidates

        except sqlite3.OperationalError as exc:
            # 如果数据库还不存在等情况
            logger.warning("稀疏检索失败 (可能暂无索引): %s", exc)
            return []
        except Exception as exc:
            logger.error("稀疏检索发生未知错误: %s", exc)
            return []
