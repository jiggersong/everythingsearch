"""测试统一配置治理。"""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace

import config
import pytest

from everythingsearch.infra import settings as settings_mod
from everythingsearch.infra.settings import (
    InvalidSettingError,
    MissingRequiredSettingError,
    apply_sdk_environment,
    get_settings,
    require_dashscope_api_key,
    require_target_dirs,
    reset_settings_cache,
)


class TestSettings:
    """测试 Settings 加载与归一化。"""

    def setup_method(self):
        reset_settings_cache()

    def teardown_method(self):
        reset_settings_cache()

    def test_env_dashscope_api_key_overrides_legacy_config(self, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "env-key")
        monkeypatch.setattr(config, "MY_API_KEY", "legacy-key")

        settings = get_settings()

        assert settings.dashscope_api_key == "env-key"

    def test_placeholder_dashscope_api_key_is_treated_as_missing(self, monkeypatch):
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        monkeypatch.setattr(config, "MY_API_KEY", "sk-your-api-key-here")

        settings = get_settings()

        assert settings.dashscope_api_key is None

    def test_target_dirs_support_string_and_are_normalized(self, monkeypatch, tmp_path):
        target_dir = tmp_path / "docs"
        target_dir.mkdir()
        monkeypatch.setattr(config, "TARGET_DIR", str(target_dir))

        settings = get_settings()

        assert settings.target_dirs == (str(target_dir.resolve()),)

    def test_target_dirs_support_list_and_deduplicate(self, monkeypatch, tmp_path):
        target_dir = tmp_path / "docs"
        target_dir.mkdir()
        monkeypatch.setattr(config, "TARGET_DIR", [str(target_dir), str(target_dir)])

        settings = get_settings()

        assert settings.target_dirs == (str(target_dir.resolve()),)

    def test_enable_mweb_false_ignores_empty_mweb_dir(self, monkeypatch):
        monkeypatch.setattr(config, "ENABLE_MWEB", False)
        monkeypatch.setattr(config, "MWEB_DIR", "")

        settings = get_settings()

        assert settings.enable_mweb is False
        assert settings.mweb_dir is None

    def test_invalid_port_raises_clear_error(self, monkeypatch):
        monkeypatch.setattr(config, "PORT", 70000, raising=False)

        with pytest.raises(InvalidSettingError) as exc_info:
            get_settings()

        assert "PORT" in str(exc_info.value)

    def test_missing_target_dir_does_not_block_base_settings_loading(self, monkeypatch):
        monkeypatch.setattr(config, "TARGET_DIR", "")

        settings = get_settings()

        assert settings.target_dirs == ()

    def test_require_target_dirs_raises_clear_error(self, monkeypatch):
        monkeypatch.setattr(config, "TARGET_DIR", "")

        with pytest.raises(MissingRequiredSettingError) as exc_info:
            require_target_dirs()

        assert "TARGET_DIR" in str(exc_info.value)

    def test_reset_settings_cache_allows_reloading(self, monkeypatch):
        monkeypatch.setattr(config, "API_MAX_READ_BYTES", 64, raising=False)
        first_settings = get_settings()
        monkeypatch.setattr(config, "API_MAX_READ_BYTES", 32, raising=False)

        assert get_settings() is first_settings

        reset_settings_cache()
        reloaded_settings = get_settings()

        assert reloaded_settings.api_max_read_bytes == 32

    def test_apply_sdk_environment_writes_normalized_key(self, monkeypatch):
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        monkeypatch.setattr(config, "MY_API_KEY", "legacy-key")

        settings = get_settings()

        apply_sdk_environment(settings)

        assert settings.dashscope_api_key == "legacy-key"
        assert settings_mod.os.environ["DASHSCOPE_API_KEY"] == "legacy-key"

    def test_apply_sdk_environment_clears_stale_env_when_key_missing(self, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "stale-key")
        settings = SimpleNamespace(dashscope_api_key=None)

        apply_sdk_environment(settings)

        assert "DASHSCOPE_API_KEY" not in settings_mod.os.environ

    def test_default_enable_mweb_is_false_without_legacy_config(self, monkeypatch):
        monkeypatch.setattr(settings_mod, "_load_legacy_config", lambda: None)
        monkeypatch.delenv("ENABLE_MWEB", raising=False)
        monkeypatch.delenv("TARGET_DIR", raising=False)

        settings = get_settings()

        assert settings.enable_mweb is False

    def test_require_dashscope_api_key_raises_when_missing(self, monkeypatch):
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
        monkeypatch.setattr(config, "MY_API_KEY", "")

        with pytest.raises(MissingRequiredSettingError):
            require_dashscope_api_key()

    def test_search_timeout_seconds_reads_from_legacy_config(self, monkeypatch):
        monkeypatch.setattr(config, "SEARCH_TIMEOUT_SECONDS", 45, raising=False)

        settings = get_settings()

        assert settings.search_timeout_seconds == 45

    def test_env_search_timeout_seconds_overrides_legacy_config(self, monkeypatch):
        monkeypatch.setenv("SEARCH_TIMEOUT_SECONDS", "12")
        monkeypatch.setattr(config, "SEARCH_TIMEOUT_SECONDS", 45, raising=False)

        settings = get_settings()

        assert settings.search_timeout_seconds == 12

    def test_negative_search_timeout_seconds_raises_invalid_setting(self, monkeypatch):
        monkeypatch.setattr(config, "SEARCH_TIMEOUT_SECONDS", -1, raising=False)

        with pytest.raises(InvalidSettingError) as exc_info:
            get_settings()

        assert "SEARCH_TIMEOUT_SECONDS" in str(exc_info.value)

    def test_position_weights_is_read_only_mapping(self):
        settings = get_settings()

        assert isinstance(settings.position_weights, MappingProxyType)

        with pytest.raises(TypeError):
            settings.position_weights["filename"] = 0.5

    def test_invalid_position_weights_value_raises_invalid_setting(self, monkeypatch):
        monkeypatch.setattr(config, "POSITION_WEIGHTS", {"filename": "oops"}, raising=False)

        with pytest.raises(InvalidSettingError) as exc_info:
            get_settings()

        assert "POSITION_WEIGHTS" in str(exc_info.value)
