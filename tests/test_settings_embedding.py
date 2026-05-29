"""Embedding 相关配置加载测试。"""

from __future__ import annotations

import pytest

pytest.importorskip("config")

from everythingsearch.infra.settings import InvalidSettingError, get_settings, reset_settings_cache


class TestEmbeddingSettings:
    def setup_method(self):
        reset_settings_cache()

    def teardown_method(self):
        reset_settings_cache()

    def test_embedding_env_vars_loaded(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-v4")
        monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1024")
        monkeypatch.setenv("EMBED_RATE_RPS_LIMIT", "15")
        monkeypatch.setenv("EMBED_MAX_INFLIGHT", "4")
        monkeypatch.setenv("TITLE_PATH_MAX_DEPTH", "2")

        settings = get_settings()

        assert settings.embedding_model == "text-embedding-v4"
        assert settings.embedding_dimensions == 1024
        assert settings.embed_rate_rps_limit == 15.0
        assert settings.embed_max_inflight == 4
        assert settings.title_path_max_depth == 2

    def test_invalid_vector_storage_format_raises(self, monkeypatch):
        monkeypatch.setenv("EMBED_VECTOR_STORAGE_FORMAT", "json")
        with pytest.raises(InvalidSettingError):
            get_settings()

    def test_float16_storage_format_rejected(self, monkeypatch):
        monkeypatch.setenv("EMBED_VECTOR_STORAGE_FORMAT", "blob_float16")
        with pytest.raises(InvalidSettingError):
            get_settings()
