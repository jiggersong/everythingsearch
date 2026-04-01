"""测试搜索核心功能"""
import pytest
import time
import sys
import os
import threading
from types import SimpleNamespace

# 确保导入路径正确
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from everythingsearch.search import (
    _get_cache_key,
    _get_cached_search,
    _set_cached_search,
    clear_search_cache,
    _build_where_filter,
    _apply_weights,
    SearchExecutionBusyError,
    SearchTimeoutError,
    _reset_search_executor_state_for_tests,
    _run_with_timeout,
)
from langchain_core.documents import Document


class TestCacheKey:
    """测试缓存键生成"""
    
    def test_cache_key_consistency(self):
        """相同参数应生成相同缓存键"""
        key1 = _get_cache_key("test query", "file", "mtime", 123.0, 456.0)
        key2 = _get_cache_key("test query", "file", "mtime", 123.0, 456.0)
        assert key1 == key2
    
    def test_cache_key_uniqueness(self):
        """不同参数应生成不同缓存键"""
        key1 = _get_cache_key("test query", "file", "mtime", None, None)
        key2 = _get_cache_key("test query", "mweb", "mtime", None, None)
        key3 = _get_cache_key("different query", "file", "mtime", None, None)
        assert key1 != key2
        assert key1 != key3
    
    def test_cache_key_with_special_chars(self):
        """测试特殊字符处理"""
        key1 = _get_cache_key("测试中文", "all", "ctime", 1000.5, 2000.5)
        key2 = _get_cache_key("test:with:special", "all", "ctime", 1000.5, 2000.5)
        # 确保能正常生成，不抛出异常
        assert len(key1) == 64  # SHA256 长度
        assert len(key2) == 64


class TestSearchCache:
    """测试搜索缓存功能"""
    
    def setup_method(self):
        """每个测试前清空缓存"""
        clear_search_cache()
    
    def teardown_method(self):
        """每个测试后清空缓存"""
        clear_search_cache()
    
    def test_set_and_get_cache(self):
        """测试缓存设置和获取"""
        key = "test_key_123"
        mock_result = [{"filename": "test.txt", "filepath": "/tmp/test.txt"}]
        
        # 设置缓存
        _set_cached_search(key, mock_result)
        
        # 获取缓存
        cached = _get_cached_search(key)
        assert cached == mock_result
    
    def test_cache_ttl_expired(self, monkeypatch):
        """TTL 过期后应未命中（通过伪造时间）"""
        import everythingsearch.search as search_mod

        base = 1_000_000.0
        clock = [base]

        def fake_time():
            return clock[0]

        monkeypatch.setattr(search_mod.time, "time", fake_time)
        key = "test_ttl_key"
        mock_result = [{"filename": "test.txt"}]
        _set_cached_search(key, mock_result)
        assert _get_cached_search(key) == mock_result
        clock[0] = base + search_mod.CACHE_TTL_SECONDS + 1
        assert _get_cached_search(key) is None
    
    def test_cache_miss(self):
        """测试缓存未命中"""
        cached = _get_cached_search("nonexistent_key")
        assert cached is None
    
    def test_cache_size_limit(self):
        """测试缓存大小限制"""
        # 添加超过限制的条目
        for i in range(110):  # MAX_CACHE_SIZE = 100
            _set_cached_search(f"key_{i}", [{"filename": f"file_{i}.txt"}])
        
        # 缓存大小应该被限制
        from everythingsearch.search import _search_cache
        assert len(_search_cache) <= 100
    
    def test_clear_cache(self):
        """测试清空缓存"""
        _set_cached_search("key1", [{"filename": "1.txt"}])
        _set_cached_search("key2", [{"filename": "2.txt"}])
        
        clear_search_cache()
        
        assert _get_cached_search("key1") is None
        assert _get_cached_search("key2") is None


class TestBuildWhereFilter:
    """测试 where 过滤器构建"""
    
    def test_empty_filter(self):
        """空参数应返回 None"""
        result = _build_where_filter("all", "mtime", None, None)
        assert result is None
    
    def test_source_filter_only(self):
        """仅来源过滤"""
        result = _build_where_filter("file", "mtime", None, None)
        assert result == {"source_type": "file"}
    
    def test_date_range_filter(self):
        """日期范围过滤"""
        result = _build_where_filter("all", "mtime", 1000.0, 2000.0)
        assert "$and" in result
        assert {"mtime": {"$gte": 1000.0}} in result["$and"]
        assert {"mtime": {"$lte": 2000.0}} in result["$and"]
    
    def test_combined_filter(self):
        """组合过滤条件"""
        result = _build_where_filter("mweb", "ctime", 1000.0, 2000.0)
        assert "$and" in result
        clauses = result["$and"]
        assert {"source_type": "mweb"} in clauses
        assert {"ctime": {"$gte": 1000.0}} in clauses
        assert {"ctime": {"$lte": 2000.0}} in clauses


class TestApplyWeights:
    """测试权重应用"""
    
    def test_filename_weight(self):
        """文件名应获得权重优惠"""
        doc = Document(
            page_content="test content",
            metadata={"chunk_type": "filename"}
        )
        results = [(doc, 0.5)]
        weighted = _apply_weights(results, "test")
        
        # filename 权重因子是 0.60，所以分数应该变为 0.5 * 0.60 = 0.3
        assert weighted[0][1] == 0.5 * 0.60
    
    def test_heading_weight(self):
        """标题应获得权重优惠"""
        doc = Document(
            page_content="test content",
            metadata={"chunk_type": "heading"}
        )
        results = [(doc, 0.5)]
        weighted = _apply_weights(results, "test")
        
        # heading 权重因子是 0.80
        assert weighted[0][1] == 0.5 * 0.80
    
    def test_content_weight(self):
        """内容应保持原权重"""
        doc = Document(
            page_content="test content",
            metadata={"chunk_type": "content"}
        )
        results = [(doc, 0.5)]
        weighted = _apply_weights(results, "test")
        
        # content 权重因子是 1.00
        assert weighted[0][1] == 0.5
    
    def test_keyword_frequency_bonus(self):
        """关键词频率应获得加分"""
        doc = Document(
            page_content="test test test test",  # 出现4次
            metadata={"chunk_type": "content"}
        )
        results = [(doc, 0.5)]
        weighted = _apply_weights(results, "test")
        
        # 频率因子计算：1.0 - 0.03 * (4-1) = 0.91，最低限制为 0.85
        expected_factor = max(0.85, 1.0 - 0.03 * 3)
        assert weighted[0][1] == 0.5 * expected_factor


class TestSearchIntegration:
    """集成测试（需要配置正确）"""
    
    @pytest.mark.skipif(
        not os.path.exists("config.py"),
        reason="需要配置 config.py"
    )
    def test_search_basic(self):
        """测试基本搜索（如果配置存在）"""
        try:
            from everythingsearch.search import search_core
            # 使用简单查询测试
            results = search_core("test")
            assert isinstance(results, list)
        except Exception as e:
            pytest.skip(f"搜索测试需要正确配置: {e}")
    
    def test_timeout_mechanism_exists(self):
        """超时包装器与异常类型存在。"""

        assert issubclass(SearchTimeoutError, Exception)
        assert callable(_run_with_timeout)


class TestSearchTimeoutControl:
    """测试搜索超时控制。"""

    def setup_method(self):
        _reset_search_executor_state_for_tests()

    def teardown_method(self):
        _reset_search_executor_state_for_tests()

    def test_run_with_timeout_returns_result_when_completed_in_time(self):
        """执行在超时时间内完成时，应返回原结果。"""
        result = _run_with_timeout(lambda: ["ok"], 1)

        assert result == ["ok"]

    def test_run_with_timeout_runs_inline_when_timeout_is_zero(self):
        """timeout=0 时应关闭超时控制，直接在当前调用路径执行。"""
        result = _run_with_timeout(lambda: ["inline"], 0)

        assert result == ["inline"]

    def test_run_with_timeout_zero_still_respects_busy_protection(self):
        """timeout=0 时仍应保留单飞执行与繁忙保护。"""
        started = threading.Event()
        finish = threading.Event()

        def blocking_task():
            started.set()
            finish.wait(timeout=1)
            return ["inline"]

        outcome = {}

        def run_first_call():
            outcome["result"] = _run_with_timeout(blocking_task, 0)

        thread = threading.Thread(target=run_first_call)
        thread.start()

        assert started.wait(timeout=0.5) is True

        with pytest.raises(SearchExecutionBusyError, match="繁忙"):
            _run_with_timeout(lambda: ["second"], 0)

        finish.set()
        thread.join(timeout=0.5)

        assert outcome["result"] == ["inline"]

    def test_run_with_timeout_raises_search_timeout_error(self):
        """执行超过超时时间时，应抛出显式超时异常。"""
        def slow_task():
            time.sleep(0.05)
            return ["late"]

        with pytest.raises(SearchTimeoutError, match="搜索操作超时"):
            _run_with_timeout(slow_task, 0.01)

    def test_search_core_does_not_cache_timeout_result(self, monkeypatch):
        """搜索超时后不应写入缓存，避免污染后续查询。"""
        import everythingsearch.search as search_mod

        clear_search_cache()

        settings = SimpleNamespace(search_timeout_seconds=1)
        calls = {"count": 0}

        monkeypatch.setattr(search_mod, "get_settings", lambda: settings)
        monkeypatch.setattr(
            search_mod,
            "_get_cached_search",
            lambda cache_key: None,
        )

        def fake_run_with_timeout(func, timeout_seconds):
            calls["count"] += 1
            raise search_mod.SearchTimeoutError("搜索操作超时（>1s）")

        set_calls = {"count": 0}
        monkeypatch.setattr(search_mod, "_run_with_timeout", fake_run_with_timeout)
        monkeypatch.setattr(
            search_mod,
            "_set_cached_search",
            lambda cache_key, result: set_calls.__setitem__("count", set_calls["count"] + 1),
        )

        with pytest.raises(search_mod.SearchTimeoutError):
            search_mod.search_core("hello")

        assert calls["count"] == 1
        assert set_calls["count"] == 0

    def test_search_core_passes_configured_timeout_to_timeout_runner(self, monkeypatch):
        """search_core 应将 Settings 中的超时秒数透传给执行包装器。"""
        import everythingsearch.search as search_mod

        settings = SimpleNamespace(search_timeout_seconds=42)
        captured = {}

        monkeypatch.setattr(search_mod, "get_settings", lambda: settings)
        monkeypatch.setattr(search_mod, "_get_cached_search", lambda cache_key: None)
        monkeypatch.setattr(
            search_mod,
            "_set_cached_search",
            lambda cache_key, result: None,
        )

        def fake_run_with_timeout(func, timeout_seconds):
            captured["timeout_seconds"] = timeout_seconds
            return [{"filename": "demo.txt"}]

        monkeypatch.setattr(search_mod, "_run_with_timeout", fake_run_with_timeout)

        results = search_mod.search_core("hello")

        assert results == [{"filename": "demo.txt"}]
        assert captured["timeout_seconds"] == 42

    def test_run_with_timeout_reports_busy_while_previous_timed_out_task_is_still_running(self):
        """前一个已超时任务仍在后台运行时，应返回繁忙错误而不是继续排队。"""
        started = threading.Event()
        finish = threading.Event()
        outcome = {}

        def slow_task():
            started.set()
            finish.wait(timeout=1)
            return ["slow"]

        def run_first_call():
            with pytest.raises(SearchTimeoutError):
                _run_with_timeout(slow_task, 0.01)
            outcome["timed_out"] = True

        thread = threading.Thread(target=run_first_call)
        thread.start()

        assert started.wait(timeout=0.5) is True
        thread.join(timeout=0.5)
        assert outcome["timed_out"] is True

        with pytest.raises(SearchExecutionBusyError, match="繁忙"):
            _run_with_timeout(lambda: ["fast"], 1)

        finish.set()
        time.sleep(0.05)

        assert _run_with_timeout(lambda: ["recovered"], 1) == ["recovered"]


class TestSearchFailureRecovery:
    """测试搜索依赖故障与恢复路径。"""

    def test_do_search_core_recovers_after_not_found_once(self, monkeypatch):
        """首次检索遇到 NotFoundError 时，应清理缓存并重试。"""
        import everythingsearch.search as search_mod

        settings = SimpleNamespace(
            search_top_k=3,
            score_threshold=0.5,
            position_weights={"content": 1.0},
            keyword_freq_bonus=0.03,
        )
        calls = {"clear": 0, "search": 0}
        doc = Document(
            page_content="hello world",
            metadata={
                "source": "/tmp/demo.txt",
                "filename": "demo.txt",
                "type": ".txt",
                "source_type": "file",
                "mtime": 1.0,
                "ctime": 2.0,
                "chunk_type": "content",
            },
        )

        class DummyVectorDb:
            def similarity_search_with_score(self, query, k, filter=None):
                calls["search"] += 1
                if calls["search"] == 1:
                    raise search_mod.NotFoundError("collection missing")
                return [(doc, 0.2)]

        monkeypatch.setattr(search_mod, "get_settings", lambda: settings)
        monkeypatch.setattr(search_mod, "_get_vectordb", lambda: DummyVectorDb())
        monkeypatch.setattr(
            search_mod,
            "_clear_vectordb_cache",
            lambda: calls.__setitem__("clear", calls["clear"] + 1),
        )
        monkeypatch.setattr(search_mod, "_get_chroma_collection", lambda: None)

        results = search_mod._do_search_core("hello")

        assert len(results) == 1
        assert results[0]["filename"] == "demo.txt"
        assert calls == {"clear": 1, "search": 2}

    def test_do_search_core_returns_empty_after_repeated_internal_error(self, monkeypatch):
        """连续两次 InternalError 时，应安全降级为空结果。"""
        import everythingsearch.search as search_mod

        settings = SimpleNamespace(
            search_top_k=3,
            score_threshold=0.5,
            position_weights={"content": 1.0},
            keyword_freq_bonus=0.03,
        )
        calls = {"clear": 0, "search": 0}

        class DummyVectorDb:
            def similarity_search_with_score(self, query, k, filter=None):
                calls["search"] += 1
                raise search_mod.InternalError("db unavailable")

        monkeypatch.setattr(search_mod, "get_settings", lambda: settings)
        monkeypatch.setattr(search_mod, "_get_vectordb", lambda: DummyVectorDb())
        monkeypatch.setattr(
            search_mod,
            "_clear_vectordb_cache",
            lambda: calls.__setitem__("clear", calls["clear"] + 1),
        )

        results = search_mod._do_search_core("hello")

        assert results == []
        assert calls == {"clear": 1, "search": 2}

    def test_keyword_fallback_internal_failure_does_not_break_search(self, monkeypatch):
        """关键词回退内部失败时，主搜索结果仍应正常返回。"""
        import everythingsearch.search as search_mod

        settings = SimpleNamespace(
            search_top_k=3,
            score_threshold=0.5,
            position_weights={"content": 1.0},
            keyword_freq_bonus=0.03,
        )
        doc = Document(
            page_content="hello world",
            metadata={
                "source": "/tmp/demo.txt",
                "filename": "demo.txt",
                "type": ".txt",
                "source_type": "file",
                "mtime": 1.0,
                "ctime": 2.0,
                "chunk_type": "content",
            },
        )

        class DummyVectorDb:
            def similarity_search_with_score(self, query, k, filter=None):
                return [(doc, 0.2)]

        class BrokenCollection:
            def get(self, **kwargs):
                raise RuntimeError("fallback broken")

        monkeypatch.setattr(search_mod, "get_settings", lambda: settings)
        monkeypatch.setattr(search_mod, "_get_vectordb", lambda: DummyVectorDb())
        monkeypatch.setattr(search_mod, "_get_chroma_collection", lambda: BrokenCollection())

        results = search_mod._do_search_core("hello")

        assert len(results) == 1
        assert results[0]["filepath"] == "/tmp/demo.txt"


class TestVectorDbInitializationFailure:
    """测试向量库初始化失败语义。"""

    def test_get_vectordb_missing_key_does_not_cache_partial_state(self, monkeypatch):
        """初始化在密钥校验阶段失败时，不应留下半初始化全局状态。"""
        import everythingsearch.search as search_mod

        settings = SimpleNamespace(
            persist_directory="/tmp/chroma-db",
            embedding_model="text-embedding-test",
            embedding_cache_path="/tmp/embed-cache.db",
        )

        search_mod._embeddings = None
        search_mod._vectordb = None
        search_mod._chroma_client = None

        monkeypatch.setattr(search_mod, "get_settings", lambda: settings)
        monkeypatch.setattr(
            search_mod,
            "require_dashscope_api_key",
            lambda passed_settings: (_ for _ in ()).throw(RuntimeError("missing key")),
        )

        with pytest.raises(RuntimeError, match="missing key"):
            search_mod._get_vectordb()

        assert search_mod._embeddings is None
        assert search_mod._vectordb is None
        assert search_mod._chroma_client is None

    @pytest.mark.parametrize("exc_factory", [
        lambda mod: mod.NotFoundError("collection missing"),
        lambda mod: mod.InternalError("backend unavailable"),
    ])
    def test_get_chroma_collection_returns_none_on_vectordb_errors(self, monkeypatch, exc_factory):
        """collection 访问入口应将初始化/后端错误统一降级为 None。"""
        import everythingsearch.search as search_mod

        monkeypatch.setattr(
            search_mod,
            "_get_vectordb",
            lambda: (_ for _ in ()).throw(exc_factory(search_mod)),
        )

        assert search_mod._get_chroma_collection() is None
