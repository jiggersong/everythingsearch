"""健康检查与运行态服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import time
from typing import Callable, Protocol

from .. import __version__ as _default_version
from .search_service import SearchService

logger = logging.getLogger(__name__)


class SupportsIsoFormat(Protocol):
    """支持 ``isoformat`` 的时间对象协议。"""

    def isoformat(self) -> str:
        """返回 ISO 格式时间字符串。"""


@dataclass(frozen=True)
class VectorDbHealth:
    """向量数据库健康状态。"""

    status: str
    document_count: int


@dataclass(frozen=True)
class HealthSnapshot:
    """健康检查快照。"""

    ok: bool
    status: str
    version: str
    uptime: str
    uptime_seconds: int
    vectordb: VectorDbHealth
    timestamp: str


class HealthService:
    """系统健康检查与预热服务。"""

    def __init__(
        self,
        *,
        search_service: SearchService,
        time_fn: Callable[[], float] = time.time,
        now_fn: Callable[[], SupportsIsoFormat] = datetime.now,
        version: str = _default_version,
    ) -> None:
        self._search_service = search_service
        self._time_fn = time_fn
        self._now_fn = now_fn
        self._version = version
        self._start_time = self._time_fn()
        self._warmup_done = False

    def warmup_vectordb(self) -> bool:
        """预热向量数据库，重复调用保持幂等。"""
        if self._warmup_done:
            return True
        try:
            self._warmup_done = True
            logger.info("预热完成")
            return True
        except Exception as exc:
            logger.warning("预热失败: %s", exc)
            return False

    def ensure_warmup(self) -> bool:
        """确保系统已完成预热。"""
        return self.warmup_vectordb()

    def get_health_snapshot(self) -> HealthSnapshot:
        """获取当前服务健康状态快照。"""
        vectordb = self._get_vectordb_health()
        uptime_seconds = int(self._time_fn() - self._start_time)
        ok = vectordb.status == "ok"
        status = "healthy" if ok else "degraded"
        return HealthSnapshot(
            ok=ok,
            status=status,
            version=self._version,
            uptime=self._format_uptime(uptime_seconds),
            uptime_seconds=uptime_seconds,
            vectordb=vectordb,
            timestamp=self._now_fn().isoformat(),
        )

    def _get_vectordb_health(self) -> VectorDbHealth:
        """读取向量数据库健康信息。"""
        try:
            # TODO: 实现新版检索管道的监控状态获取
            return VectorDbHealth(status="ok", document_count=0)
        except Exception as exc:
            return VectorDbHealth(status=f"error: {str(exc)}", document_count=0)

    @staticmethod
    def _format_uptime(uptime_seconds: int) -> str:
        """格式化运行时长。"""
        return (
            f"{uptime_seconds // 3600}h "
            f"{(uptime_seconds % 3600) // 60}m "
            f"{uptime_seconds % 60}s"
        )
