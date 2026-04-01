"""测试 PHASE5 C 的配置迁移。"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from everythingsearch import incremental as incremental_mod
from everythingsearch import indexer as indexer_mod
from everythingsearch import search as search_mod

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _has_direct_config_import(module_path: Path) -> bool:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.Import)
        and any(alias.name == "config" for alias in node.names)
        for node in ast.walk(tree)
    ) or any(
        isinstance(node, ast.ImportFrom)
        and node.module == "config"
        for node in ast.walk(tree)
    )


class TestPhase5ConfigMigration:
    """测试 PHASE5 C 的核心迁移点。"""

    def test_phase5_c_modules_have_no_direct_config_import(self):
        """已迁移的搜索与索引主路径不应再直接 import config。"""
        module_paths = [
            _PROJECT_ROOT / "everythingsearch" / "search.py",
            _PROJECT_ROOT / "everythingsearch" / "indexer.py",
            _PROJECT_ROOT / "everythingsearch" / "incremental.py",
        ]

        for module_path in module_paths:
            assert _has_direct_config_import(module_path) is False, module_path.name

    def test_search_get_vectordb_uses_settings_and_sdk_adapters(self, monkeypatch):
        """搜索链路应通过 Settings 和统一 SDK 适配初始化向量库。"""
        settings = SimpleNamespace(
            persist_directory="/tmp/chroma-db",
            embedding_model="text-embedding-test",
            embedding_cache_path="/tmp/embed-cache.db",
        )
        calls: list[tuple] = []
        dummy_client = object()
        dummy_embeddings = object()
        dummy_vectordb = object()

        monkeypatch.setattr(search_mod, "get_settings", lambda: settings)
        monkeypatch.setattr(
            search_mod,
            "require_dashscope_api_key",
            lambda passed_settings: calls.append(("require", passed_settings)) or "api-key",
        )
        monkeypatch.setattr(
            search_mod,
            "apply_sdk_environment",
            lambda passed_settings: calls.append(("apply", passed_settings)),
        )
        monkeypatch.setattr(
            search_mod.chromadb,
            "PersistentClient",
            lambda *, path: calls.append(("client", path)) or dummy_client,
        )
        monkeypatch.setattr(
            search_mod,
            "CachedEmbeddings",
            lambda *, model, cache_path: calls.append(("embeddings", model, cache_path)) or dummy_embeddings,
        )
        monkeypatch.setattr(
            search_mod,
            "Chroma",
            lambda *, client, embedding_function, collection_name: calls.append(
                ("chroma", client, embedding_function, collection_name)
            ) or dummy_vectordb,
        )

        search_mod._embeddings = None
        search_mod._vectordb = None
        search_mod._chroma_client = None

        vectordb = search_mod._get_vectordb()

        assert vectordb is dummy_vectordb
        assert calls == [
            ("require", settings),
            ("apply", settings),
            ("client", "/tmp/chroma-db"),
            ("embeddings", "text-embedding-test", "/tmp/embed-cache.db"),
            ("chroma", dummy_client, dummy_embeddings, "local_files"),
        ]

        search_mod._embeddings = None
        search_mod._vectordb = None
        search_mod._chroma_client = None

    def test_do_search_core_reads_settings_once_and_passes_it_downstream(self, monkeypatch):
        """单次搜索主链路应只获取一次 settings，并向下游显式传递。"""
        settings = SimpleNamespace(search_top_k=5, score_threshold=0.4)
        calls: list[tuple] = []

        class DummyVectorDb:
            def similarity_search_with_score(self, query, k, filter=None):
                calls.append(("similarity", query, k, filter))
                return [("doc", 0.2)]

        def fake_get_settings():
            calls.append(("get_settings",))
            return settings

        def fake_apply_weights(results, query, passed_settings):
            calls.append(("apply_weights", results, query, passed_settings))
            return [("weighted-doc", 0.2)]

        def fake_keyword_fallback(query, passed_settings, where_filter=None):
            calls.append(("keyword_fallback", query, passed_settings, where_filter))
            return {}

        monkeypatch.setattr(search_mod, "get_settings", fake_get_settings)
        monkeypatch.setattr(search_mod, "_get_vectordb", lambda: DummyVectorDb())
        monkeypatch.setattr(search_mod, "_apply_weights", fake_apply_weights)
        monkeypatch.setattr(
            search_mod,
            "_dedup_by_file",
            lambda results, threshold: calls.append(("dedup_by_file", results, threshold)) or {},
        )
        monkeypatch.setattr(search_mod, "_keyword_fallback", fake_keyword_fallback)

        result = search_mod._do_search_core("hello")

        assert result == []
        assert calls == [
            ("get_settings",),
            ("similarity", "hello", 10, None),
            ("apply_weights", [("doc", 0.2)], "hello", settings),
            ("dedup_by_file", [("weighted-doc", 0.2)], 0.4),
            ("keyword_fallback", "hello", settings, None),
        ]

    def test_indexer_get_splitter_is_lazy_and_uses_runtime_settings(self, monkeypatch):
        """切分器应按需构建，并使用运行时 Settings 中的分块参数。"""
        settings = SimpleNamespace(chunk_size=321, chunk_overlap=12)
        calls: list[tuple[int, int]] = []

        class DummySplitter:
            def __init__(self, *, chunk_size: int, chunk_overlap: int) -> None:
                calls.append((chunk_size, chunk_overlap))

        monkeypatch.setattr(indexer_mod, "get_settings", lambda: settings)
        monkeypatch.setattr(indexer_mod, "RecursiveCharacterTextSplitter", DummySplitter)
        monkeypatch.setattr(indexer_mod, "_splitter", None)

        first_splitter = indexer_mod._get_splitter()
        second_splitter = indexer_mod._get_splitter()

        assert first_splitter is second_splitter
        assert calls == [(321, 12)]

        monkeypatch.setattr(indexer_mod, "_splitter", None)

    def test_indexer_read_via_subprocess_passes_extension_settings(self, monkeypatch):
        """父进程应向子进程传递最小扩展名配置，而不是在子进程内重复加载 settings。"""
        settings = SimpleNamespace(
            text_extensions=frozenset({".txt", ".md"}),
            media_extensions=frozenset({".png"}),
        )
        captured: dict[str, object] = {}

        class DummyQueue:
            def get_nowait(self):
                return ("body", ["heading"])

        class DummyProcess:
            def __init__(self, *, target, args):
                captured["target"] = target
                captured["args"] = args

            def start(self):
                captured["started"] = True

            def join(self, timeout=None):
                captured.setdefault("join_calls", []).append(timeout)

            def is_alive(self):
                return False

        monkeypatch.setattr(indexer_mod, "get_settings", lambda: settings)
        monkeypatch.setattr(indexer_mod, "Queue", DummyQueue)
        monkeypatch.setattr(indexer_mod, "Process", DummyProcess)

        result = indexer_mod._read_via_subprocess("/tmp/demo.docx", ".docx")

        assert result == ("body", ["heading"])
        assert captured["started"] is True
        assert captured["args"][:4] == (
            "/tmp/demo.docx",
            ".docx",
            frozenset({".txt", ".md"}),
            frozenset({".png"}),
        )

    def test_incremental_rebuild_state_db_reads_index_path_from_settings(self, monkeypatch):
        """增量索引状态库路径应在运行时从 Settings 读取，而不是导入期绑定。"""
        settings = SimpleNamespace(index_state_db="/tmp/runtime-index-state.db")
        captured: dict[str, object] = {}

        class FakeCursor:
            def fetchall(self):
                return []

        class FakeConnection:
            def execute(self, sql, params=()):
                captured.setdefault("sql", []).append((sql, params))
                return FakeCursor()

            def commit(self):
                captured["committed"] = True

            def close(self):
                captured["closed"] = True

        monkeypatch.setattr(incremental_mod, "get_settings", lambda: settings)
        def fake_connect(path):
            captured["path"] = path
            return FakeConnection()

        monkeypatch.setattr(incremental_mod.sqlite3, "connect", fake_connect)
        monkeypatch.setattr(incremental_mod, "_scan_disk_files", lambda: {})
        monkeypatch.setattr(incremental_mod, "_scan_disk_mweb", lambda: {})

        incremental_mod._rebuild_state_db()

        assert captured["path"] == "/tmp/runtime-index-state.db"
        assert captured["committed"] is True
        assert captured["closed"] is True

    def test_incremental_requires_api_key_before_opening_state_db(self, monkeypatch):
        """增量索引应在打开状态库前完成目录与 API Key 校验。"""
        settings = SimpleNamespace(
            index_state_db="/tmp/runtime-index-state.db",
            enable_mweb=False,
            persist_directory="/tmp/chroma-db",
        )
        calls: list[tuple] = []

        class FakeConnection:
            def execute(self, sql, params=()):
                return SimpleNamespace(fetchall=lambda: [])

            def commit(self):
                return None

            def close(self):
                calls.append(("close",))

        monkeypatch.setattr(incremental_mod, "get_settings", lambda: settings)
        monkeypatch.setattr(
            incremental_mod,
            "require_target_dirs",
            lambda passed_settings: calls.append(("require_target_dirs", passed_settings)) or ("/tmp/docs",),
        )
        monkeypatch.setattr(
            incremental_mod,
            "require_dashscope_api_key",
            lambda passed_settings: calls.append(("require_dashscope_api_key", passed_settings)) or "api-key",
        )
        monkeypatch.setattr(
            incremental_mod,
            "apply_sdk_environment",
            lambda passed_settings: calls.append(("apply_sdk_environment", passed_settings)),
        )
        monkeypatch.setattr(
            incremental_mod.sqlite3,
            "connect",
            lambda path: calls.append(("sqlite_connect", path)) or FakeConnection(),
        )
        monkeypatch.setattr(incremental_mod, "_scan_disk_files", lambda: {})
        monkeypatch.setattr(incremental_mod, "_scan_disk_mweb", lambda: {})

        incremental_mod.run_incremental()

        assert calls[:4] == [
            ("require_target_dirs", settings),
            ("require_dashscope_api_key", settings),
            ("apply_sdk_environment", settings),
            ("sqlite_connect", "/tmp/runtime-index-state.db"),
        ]
