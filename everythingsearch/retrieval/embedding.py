"""向量模型适配层。"""

from __future__ import annotations

import logging
from typing import Protocol

from everythingsearch.embedding_cache import CachedEmbeddings, EmbeddingStatsSnapshot
from everythingsearch.infra.settings import Settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    """向量服务提供者协议。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """对文档集进行向量化。"""

    def embed_query(self, text: str) -> list[float]:
        """对查询文本进行向量化。"""


class DashScopeEmbeddingProvider:
    """包装后的 DashScope/CachedEmbeddings 适配器。
    
    能够根据配置决定是否启用 text_type 参数（例如 text-embedding-v4 支持）。
    由于 Langchain 的 DashScopeEmbeddings 目前可能未完全暴露 text_type，
    我们可以在不修改底层库的情况下降级，或者直接使用底层的 kwargs 支持。
    当前实现：直接包装现有的 CachedEmbeddings，并透传功能。
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._enabled_text_type = settings.embedding_text_type_enabled
        self._embeddings = None

    def _get_embeddings(self):
        if self._embeddings is None:
            from everythingsearch.infra.settings import require_dashscope_api_key
            require_dashscope_api_key(self._settings)
            from everythingsearch.embedding_cache import CachedEmbeddings
            self._embeddings = CachedEmbeddings(
                model=self._settings.embedding_model,
                cache_path=self._settings.embedding_cache_path,
                dashscope_api_key=self._settings.dashscope_api_key,
            )
        return self._embeddings

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._get_embeddings().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if not text:
            return []
        return self._get_embeddings().embed_query(text)

    def stats_snapshot(self) -> EmbeddingStatsSnapshot:
        """返回底层 CachedEmbeddings 的统计快照。"""
        if self._embeddings is None:
            return EmbeddingStatsSnapshot(
                cache_hit_text_count=0,
                uncached_text_count=0,
                remote_batch_count=0,
            )
        return self._get_embeddings().stats_snapshot()
