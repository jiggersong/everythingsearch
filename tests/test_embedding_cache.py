"""测试 Embedding 缓存功能"""
import pytest
import sys
import os
import sqlite3
import tempfile
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from embedding_cache import ConnectionPool, EmbeddingCache


class TestConnectionPool:
    """测试连接池"""
    
    @pytest.fixture
    def temp_db_path(self):
        """创建临时数据库路径"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        os.unlink(path)  # 删除文件，让连接池创建
        yield path
        # 清理
        for ext in ['', '-shm', '-wal']:
            try:
                os.unlink(path + ext)
            except:
                pass
    
    def test_pool_initialization(self, temp_db_path):
        """测试连接池初始化"""
        pool = ConnectionPool(temp_db_path, max_connections=3)
        pool.initialize()
        assert pool._initialized is True
        assert pool._pool.qsize() == 3
    
    def test_get_and_return_connection(self, temp_db_path):
        """测试获取和归还连接"""
        pool = ConnectionPool(temp_db_path, max_connections=2)
        
        conn1 = pool.get_connection()
        conn2 = pool.get_connection()
        
        # 验证连接有效
        result = conn1.execute("SELECT 1").fetchone()
        assert result[0] == 1
        
        # 归还连接
        pool.return_connection(conn1)
        pool.return_connection(conn2)
        
        # 应该能重新获取
        conn3 = pool.get_connection()
        assert conn3 is not None
    
    def test_wal_mode_enabled(self, temp_db_path):
        """测试 WAL 模式已启用"""
        pool = ConnectionPool(temp_db_path, max_connections=1)
        conn = pool.get_connection()
        
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0].lower() == "wal"


class TestEmbeddingCache:
    """测试 Embedding 缓存"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        os.unlink(path)
        yield path
        # 清理
        for ext in ['', '-shm', '-wal']:
            try:
                os.unlink(path + ext)
            except:
                pass
    
    def test_init_creates_table(self, temp_db):
        """测试初始化创建表"""
        cache = EmbeddingCache(temp_db)
        
        conn = cache._pool.get_connection()
        try:
            # 检查表是否存在
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'"
            ).fetchone()
            assert result is not None
            assert result[0] == "embeddings"
        finally:
            cache._pool.return_connection(conn)
    
    def test_put_and_get_single(self, temp_db):
        """测试单个存储和读取"""
        cache = EmbeddingCache(temp_db)
        model = "test-model"
        text = "hello world"
        vector = [0.1, 0.2, 0.3, 0.4]
        
        cache.put_many(model, [(text, vector)])
        result = cache.get_many(model, [text])
        
        assert result[text] == vector
    
    def test_put_and_get_multiple(self, temp_db):
        """测试批量存储和读取"""
        cache = EmbeddingCache(temp_db)
        model = "test-model"
        items = [
            ("text1", [0.1, 0.2]),
            ("text2", [0.3, 0.4]),
            ("text3", [0.5, 0.6]),
        ]
        
        cache.put_many(model, items)
        result = cache.get_many(model, ["text1", "text2", "text3"])
        
        assert result["text1"] == [0.1, 0.2]
        assert result["text2"] == [0.3, 0.4]
        assert result["text3"] == [0.5, 0.6]
    
    def test_get_missing_returns_none(self, temp_db):
        """测试获取不存在的键返回 None"""
        cache = EmbeddingCache(temp_db)
        model = "test-model"
        
        result = cache.get_many(model, ["nonexistent"])
        assert result["nonexistent"] is None
    
    def test_partial_cache_hit(self, temp_db):
        """测试部分缓存命中"""
        cache = EmbeddingCache(temp_db)
        model = "test-model"
        
        # 先存储部分数据
        cache.put_many(model, [("known", [1.0, 2.0])])
        
        # 查询包含已知和未知
        result = cache.get_many(model, ["known", "unknown"])
        
        assert result["known"] == [1.0, 2.0]
        assert result["unknown"] is None
    
    def test_model_isolation(self, temp_db):
        """测试不同模型数据隔离"""
        cache = EmbeddingCache(temp_db)
        
        cache.put_many("model-a", [("text", [1.0, 2.0])])
        cache.put_many("model-b", [("text", [3.0, 4.0])])
        
        result_a = cache.get_many("model-a", ["text"])
        result_b = cache.get_many("model-b", ["text"])
        
        assert result_a["text"] == [1.0, 2.0]
        assert result_b["text"] == [3.0, 4.0]
    
    def test_overwrite_existing(self, temp_db):
        """测试覆盖已存在的数据"""
        cache = EmbeddingCache(temp_db)
        model = "test-model"
        
        cache.put_many(model, [("text", [1.0, 2.0])])
        cache.put_many(model, [("text", [3.0, 4.0])])  # 覆盖
        
        result = cache.get_many(model, ["text"])
        assert result["text"] == [3.0, 4.0]
    
    def test_legacy_table_adds_created_at(self, temp_db):
        """旧库仅 text_hash/vector 两列时，初始化应迁移出 created_at"""
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "CREATE TABLE embeddings (text_hash TEXT PRIMARY KEY, vector TEXT)"
        )
        conn.commit()
        conn.close()

        EmbeddingCache(temp_db)
        conn = sqlite3.connect(temp_db)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(embeddings)").fetchall()]
        conn.close()
        assert "created_at" in cols

    def test_thread_safety(self, temp_db):
        """测试线程安全"""
        cache = EmbeddingCache(temp_db, max_connections=5)
        model = "test-model"
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(10):
                    text = f"thread{thread_id}_text{i}"
                    vector = [float(thread_id), float(i)]
                    cache.put_many(model, [(text, vector)])
                    result = cache.get_many(model, [text])
                    if result[text] != vector:
                        errors.append(f"数据不匹配: {text}")
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"线程安全测试失败: {errors}"
