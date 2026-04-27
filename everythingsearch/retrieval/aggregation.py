"""结果聚合模块。"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Protocol

from everythingsearch.retrieval.models import AggregatedResult, SearchCandidate

logger = logging.getLogger(__name__)


class ResultAggregator(Protocol):
    """结果聚合器协议。"""

    def aggregate(self, candidates: list[SearchCandidate], max_highlights: int = 3) -> list[AggregatedResult]:
        """将候选块聚合为文件级结果。"""


from everythingsearch.infra.settings import get_settings

class DefaultFileAggregator:
    """默认的文件级聚合器实现。"""

    def aggregate(self, candidates: list[SearchCandidate], max_highlights: int = 3) -> list[AggregatedResult]:
        if not candidates:
            return []
            
        settings = get_settings()

        # 按 file_id 分组
        grouped: dict[str, list[SearchCandidate]] = defaultdict(list)
        for cand in candidates:
            key = cand.file_id or cand.filepath
            grouped[key].append(cand)

        aggregated = []

        for file_id, group in grouped.items():
            # 获取每个 candidate 的基础得分
            def _get_score(c: SearchCandidate) -> float:
                return c.rerank_score if c.rerank_score is not None else c.fusion_score
                
            # 按分数值降序排列
            sorted_group = sorted(group, key=_get_score, reverse=True)
            
            best_chunk = sorted_group[0]
            
            # 计算加权分
            base_score = 0.0
            if len(sorted_group) > 0:
                base_score += _get_score(sorted_group[0]) * settings.agg_best_weight
            if len(sorted_group) > 1:
                base_score += _get_score(sorted_group[1]) * settings.agg_second_weight
            if len(sorted_group) > 2:
                base_score += _get_score(sorted_group[2]) * settings.agg_third_weight
                
            # 计算 bonuses
            bonus = 0.0
            chunk_types = {c.chunk_type for c in sorted_group}
            if "filename" in chunk_types:
                bonus += settings.agg_filename_bonus
            if "heading" in chunk_types:
                bonus += settings.agg_heading_bonus
                
            # Multi-hit bonus (hitting many chunks in the same file)
            if len(sorted_group) > 3:
                bonus += settings.agg_multi_hit_bonus * min(len(sorted_group) - 3, 5)  # Cap the bonus
                
            # TODO: exact_phrase_bonus, large_file_penalty can be added if metadata exists
            
            final_score = base_score + bonus

            # 收集高亮片段，去重并限制数量
            highlights = []
            seen_content = set()
            for cand in sorted_group:
                content = cand.content or ""
                content = content.strip()
                if content and content not in seen_content:
                    seen_content.add(content)
                    highlights.append(content)
                    if len(highlights) >= max_highlights:
                        break
            
            # 如果没有高亮内容，至少把文件名放进去
            if not highlights:
                highlights.append(f"文件命中: {best_chunk.filename}")

            agg_res = AggregatedResult(
                file_id=best_chunk.file_id,
                filename=best_chunk.filename,
                filepath=best_chunk.filepath,
                source_type=best_chunk.source_type,
                filetype=best_chunk.filetype,
                mtime=float(best_chunk.metadata.get("mtime", 0.0)),
                score=final_score,
                best_chunk_type=best_chunk.chunk_type,
                highlights=highlights,
                metadata=best_chunk.metadata
            )
            aggregated.append(agg_res)

        # 重新按照综合打分降序排列
        aggregated.sort(key=lambda x: x.score, reverse=True)
        return aggregated
