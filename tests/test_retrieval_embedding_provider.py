"""DashScope embedding provider 适配层测试。"""

from types import SimpleNamespace

from everythingsearch.embedding_cache import EmbeddingStatsSnapshot
from everythingsearch.retrieval.embedding import DashScopeEmbeddingProvider


class TestDashScopeEmbeddingProvider:
    """测试 embedding provider 的统计透传。"""

    def test_stats_snapshot_is_zero_before_lazy_initialization(self, tmp_path):
        """未创建底层 CachedEmbeddings 前应返回零值快照。"""
        settings = SimpleNamespace(
            embedding_model="text-embedding-v2",
            embedding_cache_path=str(tmp_path / "embedding.db"),
            dashscope_api_key="fake-key",
            embed_max_chars=600,
            embedding_dimensions=None,
            embedding_document_text_type="document",
            embedding_query_text_type="query",
            embed_vector_storage_format="blob_float32",
            embed_rate_rps_limit=20.0,
            embed_rate_tpm_limit=900000.0,
            embed_max_inflight=6,
            embed_retry_max=5,
            embed_backoff_base_ms=500,
            embed_backoff_max_ms=15000,
        )
        provider = DashScopeEmbeddingProvider(settings)

        snapshot = provider.stats_snapshot()

        assert snapshot == EmbeddingStatsSnapshot(0, 0, 0)

    def test_stats_snapshot_delegates_to_cached_embeddings(self, tmp_path):
        """已存在底层对象时应透传其统计快照。"""
        settings = SimpleNamespace(
            embedding_model="text-embedding-v2",
            embedding_cache_path=str(tmp_path / "embedding.db"),
            dashscope_api_key="fake-key",
            embed_max_chars=600,
            embedding_dimensions=None,
            embedding_document_text_type="document",
            embedding_query_text_type="query",
            embed_vector_storage_format="blob_float32",
            embed_rate_rps_limit=20.0,
            embed_rate_tpm_limit=900000.0,
            embed_max_inflight=6,
            embed_retry_max=5,
            embed_backoff_base_ms=500,
            embed_backoff_max_ms=15000,
        )
        provider = DashScopeEmbeddingProvider(settings)
        provider._embeddings = SimpleNamespace(
            stats_snapshot=lambda: EmbeddingStatsSnapshot(1, 2, 3)
        )

        assert provider.stats_snapshot() == EmbeddingStatsSnapshot(1, 2, 3)
