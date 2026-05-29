"""DashScope 文本向量 API 调用与错误处理（避免 requests.HTTPError 与 DashScope 响应不兼容）。"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DashScopeEmbedModelLimits:
    """单模型官方限速参考（中国内地）。"""

    rps: float
    tpm: float
    api_batch_size: int


# 中国内地默认配额（text-embedding-v1/v2/v3/v4 共用，仅输入 Token）
# 文档：https://help.aliyun.com/zh/model-studio/rate-limit
# 另有秒级 RPS/TPS 限制；突发流量仍可能触发 429。
DASHSCOPE_TEXT_EMBEDDING_MAINLAND_LIMITS: dict[str, DashScopeEmbedModelLimits] = {}


def _init_limits() -> None:
    shared = DashScopeEmbedModelLimits(rps=30.0, tpm=1_200_000.0, api_batch_size=25)
    v3_v4 = DashScopeEmbedModelLimits(rps=30.0, tpm=1_200_000.0, api_batch_size=10)
    DASHSCOPE_TEXT_EMBEDDING_MAINLAND_LIMITS.update(
        {
            "text-embedding-v1": shared,
            "text-embedding-v2": shared,
            "text-embedding-v3": DashScopeEmbedModelLimits(30.0, 1_200_000.0, 10),
            "text-embedding-v4": v3_v4,
        }
    )


_init_limits()


class EmbeddingApiError(RuntimeError):
    """DashScope Embedding API 调用失败。"""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        retriable: bool,
        request_id: str = "",
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retriable = retriable
        self.request_id = request_id
        detail = message or code or f"HTTP {status_code}"
        if request_id:
            detail = f"{detail} (request_id={request_id})"
        super().__init__(detail)

    def __str__(self) -> str:
        parts = [f"status={self.status_code}"]
        if self.code:
            parts.append(f"code={self.code}")
        if self.message:
            parts.append(self.message)
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return ", ".join(parts)


class EmbeddingApiFatalError(RuntimeError):
    """多次重试后仍无法完成 embedding。"""


def is_retriable_embedding_error(status_code: int, code: str) -> bool:
    """判断是否适合退避重试。"""
    if status_code == 429:
        return True
    if status_code >= 500:
        return True
    normalized = (code or "").strip()
    if normalized.startswith("Throttling"):
        return True
    if normalized in {"ServiceUnavailable", "InternalError"}:
        return True
    return False


def _response_field(resp: Any, key: str, default: str = "") -> str:
    value = default
    try:
        if hasattr(resp, "get") and callable(resp.get):
            value = resp.get(key, default)
        else:
            value = getattr(resp, key, default)
    except (KeyError, TypeError, AttributeError):
        value = default
    if value is None:
        return default
    if key == "status_code":
        return str(value)
    return str(value) if value != default else default


def call_dashscope_text_embeddings(
  client: Any,
  *,
  model: str,
  texts: list[str],
  text_type: str,
  dimension: int | None = None,
) -> list[list[float]]:
    """调用 DashScope TextEmbedding，成功时返回向量列表。"""
    if not texts:
        return []

    kwargs: dict[str, Any] = {
        "model": model,
        "input": texts,
        "text_type": text_type,
    }
    if dimension is not None:
        kwargs["dimension"] = dimension

    resp = client.call(**kwargs)
    status_code = int(_response_field(resp, "status_code", "0") or 0)
    code = _response_field(resp, "code")
    message = _response_field(resp, "message")
    request_id = _response_field(resp, "request_id")

    if status_code == 200:
        output = resp.output if hasattr(resp, "output") else resp.get("output")
        if output is None:
            raise EmbeddingApiError(
                status_code=status_code,
                code=code,
                message="API 返回空 output",
                retriable=True,
                request_id=request_id,
            )
        if isinstance(output, dict):
            items = output.get("embeddings")
        else:
            items = getattr(output, "embeddings", None)
        if not items:
            raise EmbeddingApiError(
                status_code=status_code,
                code=code,
                message="API 返回无 embeddings 字段",
                retriable=True,
                request_id=request_id,
            )
        vectors: list[list[float]] = []
        for item in items:
            if isinstance(item, dict):
                vec = item.get("embedding")
            else:
                vec = getattr(item, "embedding", None)
            if vec is None:
                raise EmbeddingApiError(
                    status_code=status_code,
                    code=code,
                    message="embeddings 条目缺少 embedding 字段",
                    retriable=True,
                    request_id=request_id,
                )
            vectors.append(list(vec))
        if len(vectors) != len(texts):
            raise EmbeddingApiError(
                status_code=status_code,
                code=code,
                message=f"向量条数不匹配: 期望 {len(texts)}，实际 {len(vectors)}",
                retriable=True,
                request_id=request_id,
            )
        return vectors

    retriable = is_retriable_embedding_error(status_code, code)
    raise EmbeddingApiError(
        status_code=status_code,
        code=code,
        message=message,
        retriable=retriable,
        request_id=request_id,
    )


def compute_retry_backoff_seconds(
    attempt: int,
    exc: EmbeddingApiError,
    *,
    base_ms: int,
    max_ms: int,
) -> float:
    """计算第 attempt 次失败后的等待秒数（含抖动）。"""
    if exc.status_code == 429:
        # 限流：官方说明通常 1 分钟内恢复，首次等待不低于 5s
        floor_ms = 5000
        delay_ms = min(max_ms, max(floor_ms, base_ms * (2**attempt)))
    else:
        delay_ms = min(max_ms, base_ms * (2**attempt))
    jitter = random.randint(0, max(1, delay_ms // 4))
    return (delay_ms + jitter) / 1000.0


def call_with_retry(
    client: Any,
    *,
    model: str,
    texts: list[str],
    text_type: str,
    dimension: int | None,
    retry_max: int,
    backoff_base_ms: int,
    backoff_max_ms: int,
    on_retry: Any | None = None,
) -> list[list[float]]:
    """带退避的 embedding 调用；耗尽重试后抛出 EmbeddingApiFatalError。"""
    last_exc: EmbeddingApiError | None = None
    attempts = retry_max + 1
    for attempt in range(attempts):
        try:
            return call_dashscope_text_embeddings(
                client,
                model=model,
                texts=texts,
                text_type=text_type,
                dimension=dimension,
            )
        except EmbeddingApiError as exc:
            last_exc = exc
            if not exc.retriable or attempt >= retry_max:
                break
            sleep_sec = compute_retry_backoff_seconds(
                attempt,
                exc,
                base_ms=backoff_base_ms,
                max_ms=backoff_max_ms,
            )
            if on_retry is not None:
                on_retry(attempt + 1, retry_max, exc, sleep_sec)
            else:
                logger.warning(
                    "Embedding API 失败，%ss 后重试 (%s/%s): %s",
                    sleep_sec,
                    attempt + 1,
                    retry_max,
                    exc,
                )
            time.sleep(sleep_sec)

    if last_exc is None:
        raise EmbeddingApiFatalError("Embedding API 未知失败")
    raise EmbeddingApiFatalError(
        f"Embedding API 在 {attempts} 次尝试后仍失败: {last_exc}"
    ) from last_exc
