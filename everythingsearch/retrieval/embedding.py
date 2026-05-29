"""向量模型适配层。"""

from __future__ import annotations

import logging
from typing import Protocol

from everythingsearch.embedding_cache import CachedEmbeddings, EmbeddingStatsSnapshot
from everythingsearch.infra.embed_rate_limiter import DualTokenBucketRateLimiter
from everythingsearch.infra.settings import Settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    """向量服务提供者协议。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """对文档集进行向量化。"""

    def embed_query(self, text: str) -> list[float]:
        """对查询文本进行向量化。"""


class DashScopeEmbeddingProvider:
    """包装 CachedEmbeddings，透传限流、维度与 text_type 配置。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._embeddings: CachedEmbeddings | None = None
        self._rate_limiter = DualTokenBucketRateLimiter(
            rps_limit=settings.embed_rate_rps_limit,
            tpm_limit=settings.embed_rate_tpm_limit,
            max_inflight=settings.embed_max_inflight,
        )

    def _get_embeddings(self) -> CachedEmbeddings:
        if self._embeddings is None:
            from everythingsearch.infra.settings import require_dashscope_api_key

            require_dashscope_api_key(self._settings)
            self._embeddings = CachedEmbeddings(
                model=self._settings.embedding_model,
                cache_path=self._settings.embedding_cache_path,
                dashscope_api_key=self._settings.dashscope_api_key,
                embed_max_chars=self._settings.embed_max_chars,
                embedding_dimensions=self._settings.embedding_dimensions,
                document_text_type=self._settings.embedding_document_text_type,
                query_text_type=self._settings.embedding_query_text_type,
                vector_storage_format=self._settings.embed_vector_storage_format,
                rate_limiter=self._rate_limiter,
                embed_retry_max=self._settings.embed_retry_max,
                embed_backoff_base_ms=self._settings.embed_backoff_base_ms,
                embed_backoff_max_ms=self._settings.embed_backoff_max_ms,
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
        if self._embeddings is None:
            return EmbeddingStatsSnapshot(
                cache_hit_text_count=0,
                uncached_text_count=0,
                remote_batch_count=0,
            )
        return self._embeddings.stats_snapshot()
