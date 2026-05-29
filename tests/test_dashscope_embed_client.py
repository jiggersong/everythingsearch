"""DashScope embedding 客户端与重试测试。"""

from __future__ import annotations

import pytest

from everythingsearch.infra.dashscope_embed_client import (
    EmbeddingApiError,
    EmbeddingApiFatalError,
    call_dashscope_text_embeddings,
    call_with_retry,
    compute_retry_backoff_seconds,
    is_retriable_embedding_error,
)


class FakeDashScopeResponse(dict):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, item):
        return self[item]


def test_api_failure_raises_embedding_api_error_not_keyerror():
    class Client:
        @staticmethod
        def call(**kwargs):
            return FakeDashScopeResponse(
                status_code=429,
                code="Throttling.RateQuota",
                message="Requests rate limit exceeded",
                request_id="req-123",
            )

    with pytest.raises(EmbeddingApiError) as exc_info:
        call_dashscope_text_embeddings(
            Client,
            model="text-embedding-v4",
            texts=["hello"],
            text_type="document",
            dimension=1024,
        )
    err = exc_info.value
    assert err.status_code == 429
    assert err.retriable is True
    assert "req-123" in str(err)


def test_non_retriable_401_fails_without_retry():
    calls = {"count": 0}

    class Client:
        @staticmethod
        def call(**kwargs):
            calls["count"] += 1
            return FakeDashScopeResponse(
                status_code=401,
                code="InvalidApiKey",
                message="Unauthorized",
            )

    with pytest.raises(EmbeddingApiFatalError):
        call_with_retry(
            Client,
            model="text-embedding-v4",
            texts=["hello"],
            text_type="document",
            dimension=1024,
            retry_max=3,
            backoff_base_ms=1,
            backoff_max_ms=2,
        )
    assert calls["count"] == 1


def test_retriable_error_retries_then_fails(monkeypatch):
    calls = {"count": 0}
    sleeps: list[float] = []
    monkeypatch.setattr("everythingsearch.infra.dashscope_embed_client.time.sleep", lambda s: sleeps.append(s))

    class Client:
        @staticmethod
        def call(**kwargs):
            calls["count"] += 1
            return FakeDashScopeResponse(
                status_code=429,
                code="Throttling.RateQuota",
                message="limit",
            )

    with pytest.raises(EmbeddingApiFatalError):
        call_with_retry(
            Client,
            model="text-embedding-v4",
            texts=["hello"],
            text_type="document",
            dimension=1024,
            retry_max=2,
            backoff_base_ms=10,
            backoff_max_ms=20,
        )
    assert calls["count"] == 3
    assert len(sleeps) == 2


def test_success_after_transient_failure(monkeypatch):
    calls = {"count": 0}
    monkeypatch.setattr("everythingsearch.infra.dashscope_embed_client.time.sleep", lambda _s: None)

    class Client:
        @staticmethod
        def call(**kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return FakeDashScopeResponse(
                    status_code=503,
                    code="ServiceUnavailable",
                    message="busy",
                )
            return FakeDashScopeResponse(
                status_code=200,
                output={"embeddings": [{"embedding": [0.1, 0.2]}]},
            )

    vectors = call_with_retry(
        Client,
        model="text-embedding-v4",
        texts=["hello"],
        text_type="document",
        dimension=None,
        retry_max=3,
        backoff_base_ms=1,
        backoff_max_ms=2,
    )
    assert vectors == [[0.1, 0.2]]
    assert calls["count"] == 2


def test_429_backoff_has_higher_floor():
    exc = EmbeddingApiError(
        status_code=429,
        code="Throttling.RateQuota",
        message="limit",
        retriable=True,
    )
    delay = compute_retry_backoff_seconds(0, exc, base_ms=500, max_ms=60000)
    assert delay >= 5.0


def test_text_embedding_v4_official_limits():
    from everythingsearch.infra.dashscope_embed_client import DASHSCOPE_TEXT_EMBEDDING_MAINLAND_LIMITS

    limits = DASHSCOPE_TEXT_EMBEDDING_MAINLAND_LIMITS["text-embedding-v4"]
    assert limits.rps == 30
    assert limits.tpm == 1_200_000
    assert limits.api_batch_size == 10


def test_is_retriable_mapping():
    assert is_retriable_embedding_error(429, "Throttling.RateQuota") is True
    assert is_retriable_embedding_error(500, "InternalError") is True
    assert is_retriable_embedding_error(401, "InvalidApiKey") is False
