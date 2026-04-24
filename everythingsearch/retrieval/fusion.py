"""检索结果融合模块。"""

from __future__ import annotations

import logging
from typing import Protocol

from everythingsearch.infra.settings import Settings
from everythingsearch.retrieval.models import QueryPlan, SearchCandidate

logger = logging.getLogger(__name__)


class CandidateFusion(Protocol):
    """候选融合器协议。"""

    def fuse(
        self,
        sparse_candidates: list[SearchCandidate],
        dense_candidates: list[SearchCandidate],
        plan: QueryPlan,
    ) -> list[SearchCandidate]:
        """合并两路候选集。"""


class RRFCandidateFusion:
    """基于 RRF (Reciprocal Rank Fusion) 的多路召回融合器。"""

    def __init__(self, settings: Settings) -> None:
        self._k = settings.rrf_k
        self._fusion_top_k = settings.fusion_top_k

    def fuse(
        self,
        sparse_candidates: list[SearchCandidate],
        dense_candidates: list[SearchCandidate],
        plan: QueryPlan,
    ) -> list[SearchCandidate]:
        if not sparse_candidates and not dense_candidates:
            return []

        sparse_weight, dense_weight = self._get_weights_for_query(plan.query_type)

        # 按 chunk_id 聚类合并
        fused_map: dict[str, SearchCandidate] = {}

        # 处理稀疏召回结果
        for candidate in sparse_candidates:
            # RRF 算分
            rank = candidate.sparse_rank if candidate.sparse_rank is not None else 1000
            rrf_score = sparse_weight / (self._k + rank)

            # 更新 candidate 分数
            # 此时它是字典里的一份拷贝，或者直接更新（因为 dataclass frozen=True，需要新建）
            fused_cand = SearchCandidate(
                chunk_id=candidate.chunk_id,
                file_id=candidate.file_id,
                filepath=candidate.filepath,
                filename=candidate.filename,
                chunk_type=candidate.chunk_type,
                content=candidate.content,
                title_path=candidate.title_path,
                source_type=candidate.source_type,
                filetype=candidate.filetype,
                sparse_rank=candidate.sparse_rank,
                dense_rank=None,
                sparse_score=candidate.sparse_score,
                dense_score=None,
                fusion_score=rrf_score,
                metadata=candidate.metadata,
            )
            fused_map[fused_cand.chunk_id] = fused_cand

        # 处理稠密召回结果
        for candidate in dense_candidates:
            rank = candidate.dense_rank if candidate.dense_rank is not None else 1000
            rrf_score = dense_weight / (self._k + rank)

            existing = fused_map.get(candidate.chunk_id)
            if existing:
                # 合并两路分数，并补齐缺少的排名或分数信息
                new_fusion_score = existing.fusion_score + rrf_score
                fused_map[candidate.chunk_id] = SearchCandidate(
                    chunk_id=existing.chunk_id,
                    file_id=existing.file_id,
                    filepath=existing.filepath,
                    filename=existing.filename,
                    chunk_type=existing.chunk_type,
                    content=existing.content or candidate.content, # 选择内容更全的
                    title_path=existing.title_path,
                    source_type=existing.source_type,
                    filetype=existing.filetype,
                    sparse_rank=existing.sparse_rank,
                    dense_rank=candidate.dense_rank,
                    sparse_score=existing.sparse_score,
                    dense_score=candidate.dense_score,
                    fusion_score=new_fusion_score,
                    metadata=existing.metadata,
                )
            else:
                # 新增
                fused_cand = SearchCandidate(
                    chunk_id=candidate.chunk_id,
                    file_id=candidate.file_id,
                    filepath=candidate.filepath,
                    filename=candidate.filename,
                    chunk_type=candidate.chunk_type,
                    content=candidate.content,
                    title_path=candidate.title_path,
                    source_type=candidate.source_type,
                    filetype=candidate.filetype,
                    sparse_rank=None,
                    dense_rank=candidate.dense_rank,
                    sparse_score=None,
                    dense_score=candidate.dense_score,
                    fusion_score=rrf_score,
                    metadata=candidate.metadata,
                )
                fused_map[candidate.chunk_id] = fused_cand

        # 转换为列表并按 fusion_score 降序排序
        fused_list = list(fused_map.values())
        fused_list.sort(key=lambda x: x.fusion_score, reverse=True)

        # 截断 topK
        limit = plan.fusion_top_k if plan.fusion_top_k > 0 else self._fusion_top_k
        return fused_list[:limit]

    def _get_weights_for_query(self, query_type: str) -> tuple[float, float]:
        """返回 (sparse_weight, dense_weight)。"""
        if query_type == "exact":
            return 1.4, 0.7
        elif query_type == "semantic":
            return 0.8, 1.2
        elif query_type == "filename":
            return 1.3, 0.5
        elif query_type == "code":
            return 1.2, 0.8
        else:
            # hybrid 或未知
            return 1.0, 1.0
