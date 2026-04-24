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


class DefaultFileAggregator:
    """默认的文件级聚合器实现。"""

    def aggregate(self, candidates: list[SearchCandidate], max_highlights: int = 3) -> list[AggregatedResult]:
        if not candidates:
            return []

        # 按 file_id 分组
        grouped: dict[str, list[SearchCandidate]] = defaultdict(list)
        for cand in candidates:
            # 如果极端情况没有 file_id，fallback 为 filepath
            key = cand.file_id or cand.filepath
            grouped[key].append(cand)

        aggregated = []

        for file_id, group in grouped.items():
            # 排序组内 chunk
            # 依据：如果有 rerank_rank，按它升序；如果没有，按 fusion_score 降序
            # 由于传入的 candidates 通常已经按最佳顺序排好了，
            # 我们可以直接信任传入的列表顺序（即第一项就是该文件最高分的块）
            
            # 由于传入顺序可能是混合多个文件的，同一个 file_id 里的第一个一定是在总体里排名最高的
            best_chunk = group[0]

            score = best_chunk.rerank_score if best_chunk.rerank_score is not None else best_chunk.fusion_score

            # 收集高亮片段，去重并限制数量
            highlights = []
            seen_content = set()
            for cand in group:
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
                score=score,
                best_chunk_type=best_chunk.chunk_type,
                highlights=highlights,
                metadata=best_chunk.metadata
            )
            aggregated.append(agg_res)

        # 聚合后，文件的顺序应依然按照其 best_chunk 在总体里的相对顺序
        # 即它们被加入 grouped / aggregated 列表的顺序就是正确的（因为 Python >= 3.7 dict 保留插入顺序）
        return aggregated
