"""Embedding 按 SDK 批大小申请限流槽测试。"""

from __future__ import annotations

from unittest.mock import patch

from everythingsearch.embedding_cache import CachedEmbeddings
from everythingsearch.infra.embed_rate_limiter import DualTokenBucketRateLimiter


def test_call_remote_embed_acquires_slot_per_api_batch(tmp_path):
    limiter = DualTokenBucketRateLimiter(rps_limit=100, tpm_limit=100000, max_inflight=10)
    slot_calls: list[int] = []

    class TrackingLimiter(DualTokenBucketRateLimiter):
        def request_slot(self, estimated_tokens):
            slot_calls.append(estimated_tokens)

            class _CM:
                def __enter__(self):
                    return None

                def __exit__(self, *args):
                    return False

            return _CM()

    limiter = TrackingLimiter(rps_limit=100, tpm_limit=100000, max_inflight=10)
    emb = CachedEmbeddings(
        model="text-embedding-v4",
        cache_path=str(tmp_path / "cache.db"),
        dashscope_api_key="fake",
        rate_limiter=limiter,
    )
  # 25 uncached texts -> v4 batch size 10 -> 3 API calls
    texts = [f"text-{i}" for i in range(25)]
    with patch(
        "everythingsearch.embedding_cache.embed_with_retry",
        side_effect=lambda _self, **kwargs: [
            {"embedding": [0.1, 0.2]} for _ in kwargs["input"]
        ],
    ):
        result = emb._call_remote_embed(texts, "document")

    assert len(result) == 25
    assert len(slot_calls) == 3
    assert emb.remote_batch_count == 3
