"""测试 Flask Web API"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config
import pytest
from everythingsearch.file_access import InvalidPathError
from everythingsearch.infra.settings import reset_settings_cache
from everythingsearch.services.file_service import BinaryPreviewNotAllowedError
from everythingsearch.services.health_service import HealthSnapshot, VectorDbHealth
from everythingsearch.services.search_service import (
    SearchCacheStats,
    SearchCacheClearResult,
    SearchExecutionBusyServiceError,
    SearchExecutionResult,
    SearchExecutionTimeoutError,
    SearchSourceNotAvailableError,
)

# 设置测试环境
os.environ.setdefault('FLASK_ENV', 'testing')

# 创建测试客户端
@pytest.fixture
def client():
    """创建测试客户端"""
    from everythingsearch.app import app
    app.config['TESTING'] = True
    reset_settings_cache()
    with app.test_client() as client:
        yield client
    reset_settings_cache()


@pytest.fixture
def indexed_client(tmp_path, monkeypatch):
    """创建带临时索引根目录的测试客户端。"""
    indexed_root = tmp_path / "indexed"
    indexed_root.mkdir()

    monkeypatch.setattr(config, "TARGET_DIR", [str(indexed_root)])
    monkeypatch.setattr(config, "ENABLE_MWEB", False)
    monkeypatch.setattr(config, "MWEB_DIR", "", raising=False)
    reset_settings_cache()

    from everythingsearch.app import app

    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client, indexed_root
    reset_settings_cache()


class TestHealthAPI:
    """测试健康检查 API"""
    
    def test_health_check_ok(self, client):
        """测试健康检查接口返回正常"""
        rv = client.get('/api/health')
        assert rv.status_code == 200
        
        data = rv.get_json()
        assert isinstance(data['ok'], bool)
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

    def test_health_check_uses_health_service(self, client, monkeypatch):
        """健康检查应通过 health_service 提供快照。"""
        called = {"value": False}

        def fake_get_health_snapshot():
            called["value"] = True
            return HealthSnapshot(
                ok=True,
                status="healthy",
                version="test-version",
                uptime="0h 0m 1s",
                uptime_seconds=1,
                vectordb=VectorDbHealth(status="ok", document_count=2),
                cache=SearchCacheStats(cached_queries=3, max_cache_size=100),
                timestamp="2026-04-01T00:00:00",
            )

        monkeypatch.setattr(
            "everythingsearch.app.health_service.get_health_snapshot",
            fake_get_health_snapshot,
        )

        rv = client.get('/api/health')

        assert rv.status_code == 200
        assert called["value"] is True

    def test_health_check_serializes_degraded_snapshot(self, client, monkeypatch):
        """健康检查应稳定透传 degraded 快照结构。"""
        snapshot = HealthSnapshot(
            ok=False,
            status="degraded",
            version="test-version",
            uptime="0h 1m 2s",
            uptime_seconds=62,
            vectordb=VectorDbHealth(status="not_initialized", document_count=0),
            cache=SearchCacheStats(cached_queries=1, max_cache_size=100),
            timestamp="2026-04-01T00:00:00",
        )

        monkeypatch.setattr(
            "everythingsearch.app.health_service.get_health_snapshot",
            lambda: snapshot,
        )

        rv = client.get('/api/health')

        assert rv.status_code == 200
        assert rv.get_json() == {
            "ok": False,
            "status": "degraded",
            "version": "test-version",
            "uptime": "0h 1m 2s",
            "uptime_seconds": 62,
            "vectordb": {
                "status": "not_initialized",
                "document_count": 0,
            },
            "cache": {
                "cached_queries": 1,
                "max_cache_size": 100,
            },
            "timestamp": "2026-04-01T00:00:00",
        }


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

    def test_search_invalid_source(self, client):
        """测试非法 source 参数返回 400。"""
        rv = client.get('/api/search?q=test&source=xyz')
        assert rv.status_code == 400
        data = rv.get_json()
        assert data["results"] == []
        assert "error" in data

    def test_search_invalid_date_field(self, client):
        """测试非法 date_field 参数返回 400。"""
        rv = client.get('/api/search?q=test&date_field=abc')
        assert rv.status_code == 400

    def test_search_invalid_date_from(self, client):
        """测试非法 date_from 参数返回 400。"""
        rv = client.get('/api/search?q=test&date_from=abc')
        assert rv.status_code == 400

    def test_search_invalid_date_to(self, client):
        """测试非法 date_to 参数返回 400。"""
        rv = client.get('/api/search?q=test&date_to=abc')
        assert rv.status_code == 400

    def test_search_invalid_limit(self, client):
        """测试非法 limit 参数返回 400。"""
        rv = client.get('/api/search?q=test&limit=abc')
        assert rv.status_code == 400

    def test_search_service_source_unavailable_maps_to_400(self, client, monkeypatch):
        """service 层 SearchSourceNotAvailableError 应稳定映射为 400。"""
        def fake_search(_request_obj):
            raise SearchSourceNotAvailableError("当前实例已关闭 MWeb 数据源（ENABLE_MWEB=False）")

        monkeypatch.setattr("everythingsearch.app.search_service.search", fake_search)

        rv = client.get('/api/search?q=test&source=mweb')

        assert rv.status_code == 400
        assert rv.get_json() == {
            "results": [],
            "query": "test",
            "error": "当前实例已关闭 MWeb 数据源（ENABLE_MWEB=False）",
        }

    def test_search_service_generic_failure_maps_to_500(self, client, monkeypatch):
        """service 层未处理异常应被路由包装为 500。"""
        def fake_search(_request_obj):
            raise RuntimeError("boom")

        monkeypatch.setattr("everythingsearch.app.search_service.search", fake_search)

        rv = client.get('/api/search?q=test')

        assert rv.status_code == 500
        assert rv.get_json() == {
            "results": [],
            "query": "test",
            "error": "boom",
        }

    def test_search_service_timeout_maps_to_504(self, client, monkeypatch):
        """service 层搜索超时应稳定映射为 504。"""
        def fake_search(_request_obj):
            raise SearchExecutionTimeoutError("搜索操作超时（>30s）")

        monkeypatch.setattr("everythingsearch.app.search_service.search", fake_search)

        rv = client.get('/api/search?q=test')

        assert rv.status_code == 504
        assert rv.get_json() == {
            "results": [],
            "query": "test",
            "error": "搜索操作超时（>30s）",
        }

    def test_search_service_busy_maps_to_503(self, client, monkeypatch):
        """service 层搜索繁忙应稳定映射为 503。"""
        def fake_search(_request_obj):
            raise SearchExecutionBusyServiceError("搜索执行繁忙，请稍后重试")

        monkeypatch.setattr("everythingsearch.app.search_service.search", fake_search)

        rv = client.get('/api/search?q=test')

        assert rv.status_code == 503
        assert rv.get_json() == {
            "results": [],
            "query": "test",
            "error": "搜索执行繁忙，请稍后重试",
        }


class TestNlSearchAPI:
    """测试自然语言搜索接口。"""

    def test_nl_search_non_object_json_returns_400(self, client):
        rv = client.post(
            '/api/search/nl',
            data=json.dumps([]),
            content_type='application/json',
        )

        assert rv.status_code == 400
        assert rv.get_json() == {
            "error": "请求体必须是 JSON 对象",
        }

    def test_nl_search_string_json_returns_400(self, client):
        rv = client.post(
            '/api/search/nl',
            data=json.dumps("hello"),
            content_type='application/json',
        )

        assert rv.status_code == 400
        assert rv.get_json() == {
            "error": "请求体必须是 JSON 对象",
        }


class TestInterpretAPI:
    """测试搜索结果解读接口。"""

    def test_interpret_non_object_json_returns_400(self, client):
        rv = client.post(
            '/api/search/interpret',
            data=json.dumps([]),
            content_type='application/json',
        )

        assert rv.status_code == 400
        assert rv.get_json() == {
            "error": "请求体必须是 JSON 对象",
        }

    def test_interpret_stream_non_object_json_returns_400(self, client):
        rv = client.post(
            '/api/search/interpret/stream',
            data=json.dumps(123),
            content_type='application/json',
        )

        assert rv.status_code == 400
        assert rv.get_json() == {
            "error": "请求体必须是 JSON 对象",
        }


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
        assert rv.status_code == 400
    
    def test_download_unauthorized_path(self, client):
        """测试下载未授权路径"""
        rv = client.get('/api/file/download?filepath=/etc/passwd')
        assert rv.status_code == 404

    def test_read_invalid_max_bytes(self, indexed_client):
        """测试非法 max_bytes 返回 400。"""
        client, indexed_root = indexed_client
        target = indexed_root / "note.txt"
        target.write_text("hello", encoding="utf-8")

        rv = client.get(f'/api/file/read?filepath={target}&max_bytes=abc')

        assert rv.status_code == 400

    def test_read_zero_max_bytes(self, indexed_client):
        """测试 max_bytes 为 0 返回 400。"""
        client, indexed_root = indexed_client
        target = indexed_root / "note.txt"
        target.write_text("hello", encoding="utf-8")

        rv = client.get(f'/api/file/read?filepath={target}&max_bytes=0')

        assert rv.status_code == 400

    def test_read_binary_preview_error_maps_to_400(self, client, monkeypatch):
        """二进制预览异常应被接口层稳定映射为 400。"""
        def fake_read_file_preview(_request_obj):
            raise BinaryPreviewNotAllowedError("/tmp/demo.bin")

        monkeypatch.setattr(
            "everythingsearch.app.file_service.read_file_preview",
            fake_read_file_preview,
        )

        rv = client.get('/api/file/read?filepath=/tmp/demo.bin')

        assert rv.status_code == 400
        assert rv.get_json() == {
            "ok": False,
            "error": "该文件为二进制或无法作为文本安全展示，请使用 /api/file/download",
            "filepath": "/tmp/demo.bin",
        }
    
    def test_reveal_missing_filepath(self, client):
        """测试 reveal 缺少路径"""
        rv = client.post('/api/reveal', 
                         data=json.dumps({}),
                         content_type='application/json')
        assert rv.status_code == 400
    
    def test_open_missing_filepath(self, client):
        """测试 open 缺少路径"""
        rv = client.post('/api/open',
                         data=json.dumps({}),
                         content_type='application/json')
        assert rv.status_code == 400

    def test_open_non_object_json_body_returns_400(self, client):
        """测试 open 对顶层非对象 JSON 返回 400。"""
        rv = client.post(
            '/api/open',
            data=json.dumps([]),
            content_type='application/json',
        )

        assert rv.status_code == 400
        assert rv.get_json() == {
            "ok": False,
            "error": "请求体必须是 JSON 对象",
        }

    def test_open_invalid_path_error_maps_to_400(self, client, monkeypatch):
        """文件访问层 InvalidPathError 应被 open 接口映射为 400。"""
        def fake_open_file(_request_obj):
            raise InvalidPathError("路径包含非法父级跳转")

        monkeypatch.setattr("everythingsearch.app.file_service.open_file", fake_open_file)

        rv = client.post(
            '/api/open',
            data=json.dumps({"filepath": "../escape.txt"}),
            content_type='application/json',
        )

        assert rv.status_code == 400
        assert rv.get_json() == {
            "ok": False,
            "error": "路径参数无效",
        }

    def test_read_authorized_file_uses_resolved_path(self, indexed_client):
        """测试读取授权文件时返回 canonical 路径。"""
        client, indexed_root = indexed_client
        target = indexed_root / "note.txt"
        target.write_text("hello world", encoding="utf-8")

        rv = client.get(f'/api/file/read?filepath={target}')

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["ok"] is True
        assert data["filepath"] == str(target.resolve())

    def test_read_directory_is_rejected(self, indexed_client):
        """测试目录路径不能作为文件读取。"""
        client, indexed_root = indexed_client

        rv = client.get(f'/api/file/read?filepath={indexed_root}')

        assert rv.status_code == 404

    def test_download_authorized_file(self, indexed_client):
        """测试授权文件可以下载。"""
        client, indexed_root = indexed_client
        target = indexed_root / "report.txt"
        target.write_text("download", encoding="utf-8")

        rv = client.get(f'/api/file/download?filepath={target}')

        assert rv.status_code == 200
        assert rv.headers["Content-Disposition"].startswith("attachment;")

    def test_open_authorized_file_uses_resolved_path(self, indexed_client, monkeypatch):
        """测试 open 只使用 resolved path。"""
        client, indexed_root = indexed_client
        target = indexed_root / "note.txt"
        target.write_text("open", encoding="utf-8")

        called = {}

        def fake_popen(args):
            called["args"] = args
            class DummyProcess:
                pass
            return DummyProcess()

        monkeypatch.setattr("everythingsearch.services.file_service.subprocess.Popen", fake_popen)

        rv = client.post(
            '/api/open',
            data=json.dumps({"filepath": str(target)}),
            content_type='application/json',
        )

        assert rv.status_code == 200
        assert called["args"] == ["open", str(target.resolve())]

    def test_reveal_authorized_file_uses_resolved_path(self, indexed_client, monkeypatch):
        """测试 reveal 只使用 resolved path。"""
        client, indexed_root = indexed_client
        target = indexed_root / "note.txt"
        target.write_text("reveal", encoding="utf-8")

        called = {}

        def fake_popen(args):
            called["args"] = args
            class DummyProcess:
                pass
            return DummyProcess()

        monkeypatch.setattr("everythingsearch.services.file_service.subprocess.Popen", fake_popen)

        rv = client.post(
            '/api/reveal',
            data=json.dumps({"filepath": str(target)}),
            content_type='application/json',
        )

        assert rv.status_code == 200
        assert called["args"] == ["open", "-R", str(target.resolve())]

    def test_open_unauthorized_existing_file_is_rejected(self, indexed_client):
        """测试 open 拒绝索引目录外的已存在文件。"""
        client, indexed_root = indexed_client
        outside = indexed_root.parent / "outside.txt"
        outside.write_text("secret", encoding="utf-8")

        rv = client.post(
            '/api/open',
            data=json.dumps({"filepath": str(outside)}),
            content_type='application/json',
        )

        assert rv.status_code == 404

    def test_reveal_symlink_escape_is_rejected(self, indexed_client):
        """测试 symlink 逃逸会被 reveal 接口拒绝。"""
        client, indexed_root = indexed_client
        outside = indexed_root.parent / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        symlink_path = indexed_root / "escape.txt"
        os.symlink(outside, symlink_path)

        rv = client.post(
            '/api/reveal',
            data=json.dumps({"filepath": str(symlink_path)}),
            content_type='application/json',
        )

        assert rv.status_code == 404


class TestCacheAPI:
    """测试缓存管理 API"""
    
    def test_clear_cache_endpoint(self, client, monkeypatch):
        """测试清空缓存接口"""
        called = {"value": False}

        def fake_clear_cache():
            called["value"] = True
            return SearchCacheClearResult()

        monkeypatch.setattr("everythingsearch.app.search_service.clear_cache", fake_clear_cache)

        rv = client.post('/api/cache/clear')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ok'] is True
        assert 'message' in data
        assert called["value"] is True


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
    
    def test_before_request_uses_health_service(self, client, monkeypatch):
        """before_request 应转发到 health_service.ensure_warmup。"""
        called = {"count": 0}

        def fake_ensure_warmup():
            called["count"] += 1
            return True

        monkeypatch.setattr(
            "everythingsearch.app.health_service.ensure_warmup",
            fake_ensure_warmup,
        )

        client.get("/api/health")

        assert called["count"] >= 1

    def test_main_warmup_uses_health_service(self, monkeypatch):
        """main 应通过 health_service 触发预热。"""
        from everythingsearch import app as app_module

        called = {"warmup": 0, "run": 0, "logging": 0}

        def fake_warmup():
            called["warmup"] += 1
            return True

        def fake_run(*args, **kwargs):
            called["run"] += 1

        def fake_setup_logging():
            called["logging"] += 1

        monkeypatch.setattr("everythingsearch.app.health_service.warmup_vectordb", fake_warmup)
        monkeypatch.setattr("everythingsearch.app.setup_flask_dev_daily_file_logging", fake_setup_logging)
        monkeypatch.setattr(app_module.app, "run", fake_run)

        app_module.main()

        assert called["logging"] == 1
        assert called["warmup"] == 1
        assert called["run"] == 1


class TestMWebConfig:
    """测试 MWeb 配置处理"""

    def test_mweb_disabled_rejects_source_mweb(self, indexed_client):
        """测试禁用 MWeb 时 source=mweb 返回 400。"""
        client, _ = indexed_client
        rv = client.get('/api/search?q=test&source=mweb')
        assert rv.status_code == 400

    def test_mweb_disabled_source_all_remains_valid(self, indexed_client, monkeypatch):
        """测试禁用 MWeb 时 source=all 不会触发参数校验错误。"""
        client, _ = indexed_client

        captured = {}

        def fake_search(request_obj):
            captured["query"] = request_obj.query
            captured["source"] = request_obj.source
            return SearchExecutionResult(query="test", results=[])

        monkeypatch.setattr("everythingsearch.app.search_service.search", fake_search)

        rv = client.get('/api/search?q=test&source=all')

        assert rv.status_code == 200
        assert captured["query"] == "test"
        assert captured["source"] == "all"
