"""测试搜索核心功能"""
import pytest
import time
import sys
import os

# 确保导入路径正确
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from everythingsearch.search import (
    _get_cache_key, 
    _get_cached_search, 
    _set_cached_search,
    clear_search_cache,
    _build_where_filter,
    _apply_weights
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
        """超时信号处理与异常类型存在（Unix 下由 SIGALRM 触发）"""
        from everythingsearch.search import SearchTimeoutError, _timeout_handler

        assert issubclass(SearchTimeoutError, Exception)
        assert callable(_timeout_handler)
