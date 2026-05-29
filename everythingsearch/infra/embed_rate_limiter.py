"""Embedding API 全局限流（RPS/TPM 双桶 + 并发上限）。"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Iterator


class DualTokenBucketRateLimiter:
    """RPS 与 TPM 双令牌桶，并限制最大并发请求数。"""

    def __init__(self, rps_limit: float, tpm_limit: float, max_inflight: int) -> None:
        if rps_limit <= 0:
            raise ValueError("rps_limit 必须大于 0")
        if tpm_limit <= 0:
            raise ValueError("tpm_limit 必须大于 0")
        if max_inflight <= 0:
            raise ValueError("max_inflight 必须大于 0")
        self._rps_limit = float(rps_limit)
        self._tpm_limit = float(tpm_limit)
        self._rps_tokens = self._rps_limit
        self._tpm_tokens = self._tpm_limit
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(max_inflight)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._last_refill = now
        self._rps_tokens = min(self._rps_limit, self._rps_tokens + elapsed * self._rps_limit)
        # TPM 为每分钟限额，补充速率需除以 60
        self._tpm_tokens = min(self._tpm_limit, self._tpm_tokens + elapsed * self._tpm_limit / 60.0)

    def _wait_for_tokens(self, estimated_tokens: int) -> None:
        tokens = max(1, estimated_tokens)
        while True:
            with self._lock:
                self._refill()
                if self._rps_tokens >= 1.0 and self._tpm_tokens >= tokens:
                    self._rps_tokens -= 1.0
                    self._tpm_tokens -= tokens
                    return
            time.sleep(0.02)

    @contextmanager
    def request_slot(self, estimated_tokens: int) -> Iterator[None]:
        """获取一次远端 embedding 调用的限流槽位。"""
        self._semaphore.acquire()
        try:
            self._wait_for_tokens(estimated_tokens)
            yield
        finally:
            self._semaphore.release()


def estimate_tokens_for_texts(texts: list[str]) -> int:
    """按字符数粗估 token 用量（用于 TPM 桶）。"""
    return sum(max(1, len(text) // 4) for text in texts)
