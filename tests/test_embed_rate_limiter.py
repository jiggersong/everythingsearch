"""Embedding 限流器测试。"""

from __future__ import annotations

import threading
import time

import pytest

from everythingsearch.infra.embed_rate_limiter import (
    DualTokenBucketRateLimiter,
    estimate_tokens_for_texts,
)


def test_estimate_tokens_for_texts():
  assert estimate_tokens_for_texts(["abcd", ""]) >= 2


def test_tpm_refill_rate_is_per_minute_not_per_second():
    """TPM 桶应按每分钟限额补充（elapsed * limit / 60）。"""
    limiter = DualTokenBucketRateLimiter(rps_limit=1000, tpm_limit=6000, max_inflight=10)
    limiter._tpm_tokens = 0
    limiter._last_refill = time.monotonic() - 1.0
    limiter._refill()
    assert limiter._tpm_tokens == pytest.approx(100.0, rel=0.05)


def test_rate_limiter_serializes_burst():
    limiter = DualTokenBucketRateLimiter(rps_limit=2, tpm_limit=10000, max_inflight=1)
    times: list[float] = []

    def one_call():
        with limiter.request_slot(1):
            times.append(time.monotonic())

    threads = [threading.Thread(target=one_call) for _ in range(3)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(times) == 3
    assert max(times) - min(times) >= 0.3
