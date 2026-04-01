"""统一配置加载与校验。"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Mapping

from .paths import get_project_root

_PLACEHOLDER_API_KEYS = {"", "sk-your-api-key-here"}
_SETTINGS_CACHE: "Settings | None" = None


class SettingsError(RuntimeError):
    """配置加载或校验失败。"""


class MissingRequiredSettingError(SettingsError):
    """缺少必填配置。"""


class InvalidSettingError(SettingsError):
    """配置值格式非法或越界。"""


@dataclass(frozen=True)
class Settings:
    """标准化后的运行时配置。"""

    dashscope_api_key: str | None
    target_dirs: tuple[str, ...]
    enable_mweb: bool
    mweb_library_path: str
    mweb_dir: str | None
    mweb_export_script: str | None
    host: str
    port: int
    api_max_read_bytes: int
    index_state_db: str
    scan_cache_path: str
    persist_directory: str
    embedding_cache_path: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    max_content_length: int
    search_timeout_seconds: int
    search_top_k: int
    score_threshold: float
    index_only_keywords: tuple[str, ...]
    text_extensions: frozenset[str]
    office_extensions: frozenset[str]
    media_extensions: frozenset[str]
    supported_extensions: frozenset[str]
    position_weights: Mapping[str, float]
    keyword_freq_bonus: float


def get_settings() -> Settings:
    """返回缓存的标准化配置。"""
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is None:
        _SETTINGS_CACHE = _load_settings()
    return _SETTINGS_CACHE


def reset_settings_cache() -> None:
    """清空配置缓存，供测试使用。"""
    global _SETTINGS_CACHE
    _SETTINGS_CACHE = None


def apply_sdk_environment(settings: Settings | None = None) -> None:
    """将归一化后的密钥注入 SDK 所需环境变量。"""
    normalized_settings = settings or get_settings()
    if normalized_settings.dashscope_api_key:
        os.environ["DASHSCOPE_API_KEY"] = normalized_settings.dashscope_api_key
        return
    os.environ.pop("DASHSCOPE_API_KEY", None)


def require_dashscope_api_key(settings: Settings | None = None) -> str:
    """返回 DashScope API Key，不存在则抛出明确异常。"""
    normalized_settings = settings or get_settings()
    if normalized_settings.dashscope_api_key:
        return normalized_settings.dashscope_api_key
    raise MissingRequiredSettingError(
        "未配置 DashScope API Key。请设置环境变量 DASHSCOPE_API_KEY 或在 config.py 中填写 MY_API_KEY。"
    )


def require_target_dirs(settings: Settings | None = None) -> tuple[str, ...]:
    """返回索引目录列表，不存在则抛出明确异常。"""
    normalized_settings = settings or get_settings()
    if normalized_settings.target_dirs:
        return normalized_settings.target_dirs
    raise MissingRequiredSettingError(
        "未配置 TARGET_DIR。请在环境变量 TARGET_DIR 或 config.py 中设置索引目录。"
    )


def _load_settings() -> Settings:
    legacy_config = _load_legacy_config()

    target_dirs = _load_target_dirs(legacy_config)
    enable_mweb = _load_bool("ENABLE_MWEB", legacy_config, "ENABLE_MWEB", default=False)
    
    mweb_library_path = _load_required_path(
        "MWEB_LIBRARY_PATH",
        legacy_config,
        "MWEB_LIBRARY_PATH",
        default="~/Library/Containers/com.coderforart.iOS.MWeb/Data/Library/Application Support/MWebLibrary"
    )

    mweb_dir = _load_optional_path("MWEB_DIR", legacy_config, "MWEB_DIR")
    if not mweb_dir and enable_mweb:
        mweb_dir = str(get_project_root() / "data" / "mweb_export")

    mweb_export_script = _load_optional_path(
        "MWEB_EXPORT_SCRIPT",
        legacy_config,
        "MWEB_EXPORT_SCRIPT",
    )
    if not mweb_export_script and enable_mweb:
        mweb_export_script = str(get_project_root() / "scripts" / "mweb_export.py")

    settings = Settings(
        dashscope_api_key=_load_dashscope_api_key(legacy_config),
        target_dirs=target_dirs,
        enable_mweb=enable_mweb,
        mweb_library_path=mweb_library_path,
        mweb_dir=mweb_dir if enable_mweb else None,
        mweb_export_script=mweb_export_script if enable_mweb else None,
        host=_load_str("FLASK_HOST", legacy_config, "HOST", default="127.0.0.1"),
        port=_load_int("PORT", legacy_config, "PORT", default=8000),
        api_max_read_bytes=_load_int(
            "API_MAX_READ_BYTES",
            legacy_config,
            "API_MAX_READ_BYTES",
            default=524288,
        ),
        index_state_db=_load_required_path(
            "INDEX_STATE_DB",
            legacy_config,
            "INDEX_STATE_DB",
            default=str(get_project_root() / "data" / "index_state.db"),
        ),
        scan_cache_path=_load_required_path(
            "SCAN_CACHE_PATH",
            legacy_config,
            "SCAN_CACHE_PATH",
            default=str(get_project_root() / "data" / "scan_cache.db"),
        ),
        persist_directory=_load_required_path(
            "PERSIST_DIRECTORY",
            legacy_config,
            "PERSIST_DIRECTORY",
            default=str(get_project_root() / "data" / "chroma_db"),
        ),
        embedding_cache_path=_load_required_path(
            "EMBEDDING_CACHE_PATH",
            legacy_config,
            "EMBEDDING_CACHE_PATH",
            default=str(get_project_root() / "data" / "embedding_cache.db"),
        ),
        embedding_model=_load_str(
            "EMBEDDING_MODEL",
            legacy_config,
            "EMBEDDING_MODEL",
            default="text-embedding-v2",
        ),
        chunk_size=_load_int("CHUNK_SIZE", legacy_config, "CHUNK_SIZE", default=500),
        chunk_overlap=_load_int("CHUNK_OVERLAP", legacy_config, "CHUNK_OVERLAP", default=80),
        max_content_length=_load_int(
            "MAX_CONTENT_LENGTH",
            legacy_config,
            "MAX_CONTENT_LENGTH",
            default=20000,
        ),
        search_timeout_seconds=_load_int(
            "SEARCH_TIMEOUT_SECONDS",
            legacy_config,
            "SEARCH_TIMEOUT_SECONDS",
            default=30,
        ),
        search_top_k=_load_int("SEARCH_TOP_K", legacy_config, "SEARCH_TOP_K", default=250),
        score_threshold=_load_float(
            "SCORE_THRESHOLD",
            legacy_config,
            "SCORE_THRESHOLD",
            default=0.35,
        ),
        index_only_keywords=_load_keyword_tuple(legacy_config),
        text_extensions=_load_extension_set(legacy_config, "TEXT_EXTENSIONS", default=frozenset()),
        office_extensions=_load_extension_set(legacy_config, "OFFICE_EXTENSIONS", default=frozenset()),
        media_extensions=_load_extension_set(legacy_config, "MEDIA_EXTENSIONS", default=frozenset()),
        supported_extensions=_load_supported_extensions(legacy_config),
        position_weights=_load_position_weights(legacy_config),
        keyword_freq_bonus=_load_float(
            "KEYWORD_FREQ_BONUS",
            legacy_config,
            "KEYWORD_FREQ_BONUS",
            default=0.03,
        ),
    )
    _validate_settings(settings)
    return settings


def _load_legacy_config() -> ModuleType | None:
    try:
        return importlib.import_module("config")
    except ModuleNotFoundError:
        return None


def _load_dashscope_api_key(legacy_config: ModuleType | None) -> str | None:
    raw_value = os.environ.get("DASHSCOPE_API_KEY")
    if raw_value is None and legacy_config is not None:
        raw_value = getattr(legacy_config, "MY_API_KEY", None)
    return _normalize_secret(raw_value)


def _normalize_secret(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    if normalized in _PLACEHOLDER_API_KEYS:
        return None
    return normalized or None


def _load_target_dirs(legacy_config: ModuleType | None) -> tuple[str, ...]:
    raw_env = os.environ.get("TARGET_DIR")
    if raw_env is not None:
        candidates = [raw_env]
    elif legacy_config is not None:
        raw_value = getattr(legacy_config, "TARGET_DIR", "")
        if isinstance(raw_value, (list, tuple)):
            candidates = list(raw_value)
        elif raw_value:
            candidates = [raw_value]
        else:
            candidates = []
    else:
        candidates = []

    normalized = []
    seen = set()
    for candidate in candidates:
        resolved = _normalize_path(candidate)
        if resolved and resolved not in seen:
            normalized.append(resolved)
            seen.add(resolved)
    return tuple(normalized)


def _load_bool(env_name: str, legacy_config: ModuleType | None, legacy_name: str, *, default: bool) -> bool:
    raw_value = os.environ.get(env_name)
    if raw_value is not None:
        normalized = str(raw_value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise InvalidSettingError(f"{env_name} 不是合法布尔值: {raw_value}")
    if legacy_config is not None and hasattr(legacy_config, legacy_name):
        return bool(getattr(legacy_config, legacy_name))
    return default


def _load_int(env_name: str, legacy_config: ModuleType | None, legacy_name: str, *, default: int) -> int:
    raw_value = os.environ.get(env_name)
    if raw_value is None and legacy_config is not None and hasattr(legacy_config, legacy_name):
        raw_value = getattr(legacy_config, legacy_name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise InvalidSettingError(f"{env_name or legacy_name} 不是合法整数: {raw_value}") from exc


def _load_float(env_name: str, legacy_config: ModuleType | None, legacy_name: str, *, default: float) -> float:
    raw_value = os.environ.get(env_name)
    if raw_value is None and legacy_config is not None and hasattr(legacy_config, legacy_name):
        raw_value = getattr(legacy_config, legacy_name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except (TypeError, ValueError) as exc:
        raise InvalidSettingError(f"{env_name or legacy_name} 不是合法数字: {raw_value}") from exc


def _load_str(env_name: str, legacy_config: ModuleType | None, legacy_name: str, *, default: str) -> str:
    raw_value = os.environ.get(env_name)
    if raw_value is None and legacy_config is not None and hasattr(legacy_config, legacy_name):
        raw_value = getattr(legacy_config, legacy_name)
    if raw_value is None:
        return default
    normalized = str(raw_value).strip()
    return normalized or default


def _load_optional_path(env_name: str, legacy_config: ModuleType | None, legacy_name: str) -> str | None:
    raw_value = os.environ.get(env_name)
    if raw_value is None and legacy_config is not None and hasattr(legacy_config, legacy_name):
        raw_value = getattr(legacy_config, legacy_name)
    return _normalize_path(raw_value)


def _load_required_path(
    env_name: str,
    legacy_config: ModuleType | None,
    legacy_name: str,
    *,
    default: str,
) -> str:
    raw_value = os.environ.get(env_name)
    if raw_value is None and legacy_config is not None and hasattr(legacy_config, legacy_name):
        raw_value = getattr(legacy_config, legacy_name)
    normalized = _normalize_path(raw_value)
    return normalized or _normalize_path(default) or default


def _normalize_path(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    return str(Path(text).expanduser().resolve())


def _load_keyword_tuple(legacy_config: ModuleType | None) -> tuple[str, ...]:
    if legacy_config is None:
        return ()
    raw_value = getattr(legacy_config, "INDEX_ONLY_KEYWORDS", ())
    if not isinstance(raw_value, (list, tuple, set, frozenset)):
        raise InvalidSettingError("INDEX_ONLY_KEYWORDS 必须是序列类型")
    return tuple(str(item) for item in raw_value if str(item).strip())


def _load_extension_set(
    legacy_config: ModuleType | None,
    legacy_name: str,
    *,
    default: frozenset[str],
) -> frozenset[str]:
    if legacy_config is None or not hasattr(legacy_config, legacy_name):
        return default
    raw_value = getattr(legacy_config, legacy_name)
    if not isinstance(raw_value, (set, frozenset, list, tuple)):
        raise InvalidSettingError(f"{legacy_name} 必须是集合或序列类型")
    return frozenset(str(item) for item in raw_value)


def _load_supported_extensions(legacy_config: ModuleType | None) -> frozenset[str]:
    if legacy_config is not None and hasattr(legacy_config, "SUPPORTED_EXTENSIONS"):
        raw_value = getattr(legacy_config, "SUPPORTED_EXTENSIONS")
        if not isinstance(raw_value, (set, frozenset, list, tuple)):
            raise InvalidSettingError("SUPPORTED_EXTENSIONS 必须是集合或序列类型")
        return frozenset(str(item) for item in raw_value)
    text_extensions = _load_extension_set(legacy_config, "TEXT_EXTENSIONS", default=frozenset())
    office_extensions = _load_extension_set(legacy_config, "OFFICE_EXTENSIONS", default=frozenset())
    media_extensions = _load_extension_set(legacy_config, "MEDIA_EXTENSIONS", default=frozenset())
    return text_extensions | office_extensions | media_extensions


def _load_position_weights(legacy_config: ModuleType | None) -> MappingProxyType:
    raw_value = getattr(legacy_config, "POSITION_WEIGHTS", None) if legacy_config is not None else None
    if raw_value is None:
        raw_value = {"filename": 0.60, "heading": 0.80, "content": 1.00}
    if not isinstance(raw_value, dict):
        raise InvalidSettingError("POSITION_WEIGHTS 必须是字典类型")
    try:
        normalized = {str(key): float(value) for key, value in raw_value.items()}
    except (TypeError, ValueError) as exc:
        raise InvalidSettingError("POSITION_WEIGHTS 的值必须是合法数字") from exc
    return MappingProxyType(normalized)


def _validate_settings(settings: Settings) -> None:
    if not 1 <= settings.port <= 65535:
        raise InvalidSettingError(f"PORT 超出合法范围: {settings.port}")
    if settings.api_max_read_bytes <= 0:
        raise InvalidSettingError("API_MAX_READ_BYTES 必须大于 0")
    if settings.chunk_size <= 0:
        raise InvalidSettingError("CHUNK_SIZE 必须大于 0")
    if settings.chunk_overlap < 0 or settings.chunk_overlap >= settings.chunk_size:
        raise InvalidSettingError("CHUNK_OVERLAP 必须大于等于 0 且小于 CHUNK_SIZE")
    if settings.max_content_length <= 0:
        raise InvalidSettingError("MAX_CONTENT_LENGTH 必须大于 0")
    if settings.search_timeout_seconds < 0:
        raise InvalidSettingError("SEARCH_TIMEOUT_SECONDS 必须大于等于 0")
    if settings.search_top_k <= 0:
        raise InvalidSettingError("SEARCH_TOP_K 必须大于 0")
    if not 0 <= settings.score_threshold <= 1:
        raise InvalidSettingError("SCORE_THRESHOLD 必须位于 0 到 1 之间")
    if not 0 <= settings.keyword_freq_bonus <= 1:
        raise InvalidSettingError("KEYWORD_FREQ_BONUS 必须位于 0 到 1 之间")
