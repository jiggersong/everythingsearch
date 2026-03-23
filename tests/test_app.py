"""测试 Flask Web API"""
import pytest
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 设置测试环境
os.environ.setdefault('FLASK_ENV', 'testing')

# 创建测试客户端
@pytest.fixture
def client():
    """创建测试客户端"""
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestHealthAPI:
    """测试健康检查 API"""
    
    def test_health_check_ok(self, client):
        """测试健康检查接口返回正常"""
        rv = client.get('/api/health')
        assert rv.status_code == 200
        
        data = rv.get_json()
        assert data['ok'] is True
        assert 'status' in data
        assert 'version' in data
        assert 'uptime' in data
        assert 'vectordb' in data
        assert 'cache' in data
    
    def test_health_check_structure(self, client):
        """测试健康检查数据结构"""
        rv = client.get('/api/health')
        data = rv.get_json()
        
        # 检查 vectordb 结构
        assert 'status' in data['vectordb']
        assert 'document_count' in data['vectordb']
        
        # 检查 cache 结构
        assert 'cached_queries' in data['cache']
        assert 'max_cache_size' in data['cache']


class TestSearchAPI:
    """测试搜索 API"""
    
    def test_search_empty_query(self, client):
        """测试空查询"""
        rv = client.get('/api/search?q=')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['results'] == []
    
    def test_search_no_query(self, client):
        """测试无查询参数"""
        rv = client.get('/api/search')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['results'] == []
    
    def test_search_with_query(self, client):
        """测试带查询参数"""
        rv = client.get('/api/search?q=test')
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'results' in data
        assert 'query' in data
        assert data['query'] == 'test'
        assert isinstance(data['results'], list)
    
    def test_search_with_source_filter(self, client):
        """测试来源过滤"""
        rv = client.get('/api/search?q=test&source=file')
        assert rv.status_code == 200
        data = rv.get_json()
        assert 'results' in data
    
    def test_search_with_limit(self, client):
        """测试限制结果数量"""
        rv = client.get('/api/search?q=test&limit=10')
        assert rv.status_code == 200
        data = rv.get_json()
        # 即使结果不足 10 个，也应该正常工作
        assert isinstance(data['results'], list)
        assert len(data['results']) <= 10
    
    def test_search_limit_bounds(self, client):
        """测试 limit 边界值"""
        # 过大的 limit 应该被限制
        rv = client.get('/api/search?q=test&limit=999')
        assert rv.status_code == 200
        
        # 过小的 limit 应该被限制
        rv = client.get('/api/search?q=test&limit=0')
        assert rv.status_code == 200
        
        # 负数 limit 应该被处理
        rv = client.get('/api/search?q=test&limit=-5')
        assert rv.status_code == 200


class TestFileAPI:
    """测试文件操作 API"""
    
    def test_read_unauthorized_path(self, client):
        """测试读取未授权路径"""
        rv = client.get('/api/file/read?filepath=/etc/passwd')
        assert rv.status_code == 404
    
    def test_read_nonexistent_file(self, client):
        """测试读取不存在的文件"""
        rv = client.get('/api/file/read?filepath=/tmp/nonexistent_xyz.txt')
        assert rv.status_code == 404
    
    def test_read_missing_filepath(self, client):
        """测试缺少文件路径参数"""
        rv = client.get('/api/file/read')
        assert rv.status_code == 404
    
    def test_download_unauthorized_path(self, client):
        """测试下载未授权路径"""
        rv = client.get('/api/file/download?filepath=/etc/passwd')
        assert rv.status_code == 404
    
    def test_reveal_missing_filepath(self, client):
        """测试 reveal 缺少路径"""
        rv = client.post('/api/reveal', 
                         data=json.dumps({}),
                         content_type='application/json')
        assert rv.status_code == 404
    
    def test_open_missing_filepath(self, client):
        """测试 open 缺少路径"""
        rv = client.post('/api/open',
                         data=json.dumps({}),
                         content_type='application/json')
        assert rv.status_code == 404


class TestCacheAPI:
    """测试缓存管理 API"""
    
    def test_clear_cache_endpoint(self, client):
        """测试清空缓存接口"""
        rv = client.post('/api/cache/clear')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True
        assert 'message' in data


class TestIndexPage:
    """测试主页"""
    
    def test_index_page_loads(self, client):
        """测试主页加载"""
        rv = client.get('/')
        assert rv.status_code == 200
        # 检查是否包含关键内容
        assert b'EverythingSearch' in rv.data or b'html' in rv.data


class TestWarmup:
    """测试预热功能"""
    
    def test_warmup_function_exists(self):
        """测试预热函数存在"""
        from app import _warmup_vectordb
        assert callable(_warmup_vectordb)
    
    def test_warmup_idempotent(self, client):
        """预热可重复调用且不抛错"""
        from app import _warmup_vectordb

        assert _warmup_vectordb() in (True, False)
        assert _warmup_vectordb() in (True, False)
        client.get("/api/health")


class TestMWebConfig:
    """测试 MWeb 配置处理"""
    
    def test_mweb_disabled(self, client):
        """测试 MWeb 禁用时的情况"""
        # 如果 config 中 ENABLE_MWEB=False，source=mweb 应该返回错误
        # 这取决于实际配置
        rv = client.get('/api/search?q=test&source=mweb')
        # 无论成功失败，应该返回有效响应
        assert rv.status_code in [200, 400]
