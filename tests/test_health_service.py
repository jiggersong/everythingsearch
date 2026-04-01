"""测试健康检查服务层。"""

from __future__ import annotations

from datetime import datetime

from everythingsearch.services.health_service import (
    HealthService,
    HealthSnapshot,
    VectorDbHealth,
)
from everythingsearch.services.search_service import SearchCacheStats


class DummyCollection:
    """测试用 collection。"""

    def __init__(self, count_value: int) -> None:
        self._count_value = count_value

    def count(self) -> int:
        """返回文档数。"""
        return self._count_value


class StubSearchService:
    """测试用搜索服务桩。"""

    def __init__(self, cache_stats: SearchCacheStats) -> None:
        self._cache_stats = cache_stats

    def get_cache_stats(self) -> SearchCacheStats:
        """返回缓存统计。"""
        return self._cache_stats


class TestHealthService:
    """测试健康检查服务。"""

    def test_warmup_vectordb_marks_done_after_success(self):
        """首次预热成功后应标记为完成。"""
        called = {"count": 0}

        def fake_get_vectordb():
            called["count"] += 1
            return object()

        service = HealthService(
            search_service=StubSearchService(SearchCacheStats(cached_queries=0, max_cache_size=100)),
            get_vectordb_fn=fake_get_vectordb,
        )

        assert service.warmup_vectordb() is True
        assert service.warmup_vectordb() is True
        assert called["count"] == 1

    def test_warmup_vectordb_returns_false_without_marking_done_on_failure(self):
        """预热失败时应返回 False 且不标记完成。"""
        called = {"count": 0}

        def fake_get_vectordb():
            called["count"] += 1
            raise RuntimeError("boom")

        service = HealthService(
            search_service=StubSearchService(SearchCacheStats(cached_queries=0, max_cache_size=100)),
            get_vectordb_fn=fake_get_vectordb,
        )

        assert service.warmup_vectordb() is False
        assert service.warmup_vectordb() is False
        assert called["count"] == 2

    def test_warmup_vectordb_can_recover_after_initial_failure(self):
        """首次预热失败后，后续成功应标记完成并停止重复预热。"""
        called = {"count": 0}

        def fake_get_vectordb():
            called["count"] += 1
            if called["count"] == 1:
                raise RuntimeError("temporary failure")
            return object()

        service = HealthService(
            search_service=StubSearchService(SearchCacheStats(cached_queries=0, max_cache_size=100)),
            get_vectordb_fn=fake_get_vectordb,
        )

        assert service.warmup_vectordb() is False
        assert service.warmup_vectordb() is True
        assert service.warmup_vectordb() is True
        assert called["count"] == 2

    def test_ensure_warmup_is_idempotent(self):
        """ensure_warmup 应复用幂等预热行为。"""
        called = {"count": 0}

        def fake_get_vectordb():
            called["count"] += 1
            return object()

        service = HealthService(
            search_service=StubSearchService(SearchCacheStats(cached_queries=0, max_cache_size=100)),
            get_vectordb_fn=fake_get_vectordb,
        )

        assert service.ensure_warmup() is True
        assert service.ensure_warmup() is True
        assert called["count"] == 1

    def test_get_health_snapshot_reports_healthy_when_collection_exists(self):
        """存在 collection 时应返回 healthy。"""
        service = HealthService(
            search_service=StubSearchService(SearchCacheStats(cached_queries=3, max_cache_size=100)),
            time_fn=lambda: 130.0,
            now_fn=lambda: datetime(2026, 4, 1, 12, 0, 0),
            get_chroma_collection_fn=lambda: DummyCollection(7),
            version="1.2.3",
        )
        service._start_time = 100.0

        snapshot = service.get_health_snapshot()

        assert snapshot == HealthSnapshot(
            ok=True,
            status="healthy",
            version="1.2.3",
            uptime="0h 0m 30s",
            uptime_seconds=30,
            vectordb=VectorDbHealth(status="ok", document_count=7),
            cache=SearchCacheStats(cached_queries=3, max_cache_size=100),
            timestamp="2026-04-01T12:00:00",
        )

    def test_get_health_snapshot_reports_degraded_when_collection_missing(self):
        """collection 不存在时应返回 degraded。"""
        service = HealthService(
            search_service=StubSearchService(SearchCacheStats(cached_queries=1, max_cache_size=100)),
            time_fn=lambda: 160.0,
            now_fn=lambda: datetime(2026, 4, 1, 12, 0, 0),
            get_chroma_collection_fn=lambda: None,
        )
        service._start_time = 100.0

        snapshot = service.get_health_snapshot()

        assert snapshot.ok is False
        assert snapshot.status == "degraded"
        assert snapshot.vectordb == VectorDbHealth(status="not_initialized", document_count=0)

    def test_get_health_snapshot_reports_degraded_when_collection_raises(self):
        """collection 查询异常时应返回 degraded。"""
        service = HealthService(
            search_service=StubSearchService(SearchCacheStats(cached_queries=1, max_cache_size=100)),
            get_chroma_collection_fn=lambda: (_ for _ in ()).throw(RuntimeError("db down")),
        )

        snapshot = service.get_health_snapshot()

        assert snapshot.ok is False
        assert snapshot.status == "degraded"
        assert snapshot.vectordb.status == "error: db down"
        assert snapshot.vectordb.document_count == 0

    def test_get_health_snapshot_reuses_search_service_cache_stats(self):
        """健康检查应复用搜索服务缓存统计。"""
        expected_cache = SearchCacheStats(cached_queries=5, max_cache_size=200)
        service = HealthService(
            search_service=StubSearchService(expected_cache),
            get_chroma_collection_fn=lambda: DummyCollection(1),
        )

        snapshot = service.get_health_snapshot()

        assert snapshot.cache == expected_cache

    def test_get_health_snapshot_formats_uptime_and_timestamp(self):
        """应正确格式化 uptime 和 timestamp。"""
        service = HealthService(
            search_service=StubSearchService(SearchCacheStats(cached_queries=0, max_cache_size=100)),
            time_fn=lambda: 3665.0,
            now_fn=lambda: datetime(2026, 4, 1, 1, 2, 3),
            get_chroma_collection_fn=lambda: DummyCollection(0),
        )
        service._start_time = 0.0

        snapshot = service.get_health_snapshot()

        assert snapshot.uptime == "1h 1m 5s"
        assert snapshot.timestamp == "2026-04-01T01:02:03"
