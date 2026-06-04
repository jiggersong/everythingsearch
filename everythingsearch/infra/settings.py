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
    embedding_dimensions: int | None
    embedding_document_text_type: str
    embedding_query_text_type: str
    embed_vector_storage_format: str
    embed_rate_rps_limit: float
    embed_rate_tpm_limit: float
    embed_max_inflight: int
    embed_retry_max: int
    embed_backoff_base_ms: int
    embed_backoff_max_ms: int
    title_path_max_depth: int
    title_path_max_item_chars: int
    title_path_max_chars: int
    skip_aux_chunks_for_short_files: bool
    rebuild_checkpoint_path: str
    rebuild_staging_path: str
    index_run_lock_path: str
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
    trust_proxy: bool

    # 稀疏检索 (FTS5)
    sparse_index_path: str
    sparse_top_k: int
    sparse_filename_weight: float
    sparse_path_weight: float
    sparse_heading_weight: float
    sparse_content_weight: float

    # 稠密检索与融合 (Dense & Fusion)
    dense_top_k: int
    fusion_top_k: int
    rrf_k: int

    # 重排 (Rerank)
    rerank_model: str
    rerank_top_n: int
    rerank_max_doc_chars: int

    # 魔法数字及文件聚合评分权重
    indexer_batch_size: int
    sparse_index_batch_size: int
    sparse_checkpoint_interval: int
    sparse_tokenize_workers: int
    sparse_bulk_pragma_fast: bool
    sparse_skip_fts_delete_on_fresh: bool
    embed_max_chars: int
    default_search_limit: int
    
    agg_best_weight: float
    agg_second_weight: float
    agg_third_weight: float
    agg_filename_bonus: float
    agg_heading_bonus: float
    agg_exact_bonus: float
    agg_multi_hit_bonus: float
    agg_large_file_penalty: float
    agg_recency_bonus_max: float
    agg_recency_halflife_days: int

    # 智能搜索（意图识别与结果解读；需配置 DashScope API Key）
    nl_intent_model: str
    search_interpret_model: str
    nl_timeout_sec: int
    interpret_timeout_sec: int
    nl_max_message_chars: int
    interpret_max_results: int
    rate_limit_nl_per_min: int
    rate_limit_interpret_per_min: int


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
        "未配置 DashScope API Key。请在 config.py 中填写 MY_API_KEY。"
    )


def require_target_dirs(settings: Settings | None = None) -> tuple[str, ...]:
    """返回索引目录列表，不存在则抛出明确异常。"""
    normalized_settings = settings or get_settings()
    if normalized_settings.target_dirs:
        return normalized_settings.target_dirs
    raise MissingRequiredSettingError(
        "未配置 TARGET_DIR。请在 config.py 中设置索引目录。"
    )


def _load_settings() -> Settings:
    local_config = _load_local_config()

    target_dirs = _load_target_dirs(local_config)
    enable_mweb = _load_bool(local_config, "ENABLE_MWEB", default=False)
    
    mweb_library_path = _load_required_path(
        local_config,
        "MWEB_LIBRARY_PATH",
        default="~/Library/Containers/com.coderforart.iOS.MWeb/Data/Library/Application Support/MWebLibrary"
    )

    mweb_dir = _load_optional_path(local_config, "MWEB_DIR")
    if not mweb_dir and enable_mweb:
        mweb_dir = str(get_project_root() / "data" / "mweb_export")

    mweb_export_script = _load_optional_path(local_config, "MWEB_EXPORT_SCRIPT")
    if not mweb_export_script and enable_mweb:
        mweb_export_script = str(get_project_root() / "scripts" / "mweb_export.py")

    settings = Settings(
        dashscope_api_key=_load_dashscope_api_key(local_config),
        target_dirs=target_dirs,
        enable_mweb=enable_mweb,
        mweb_library_path=mweb_library_path,
        mweb_dir=mweb_dir if enable_mweb else None,
        mweb_export_script=mweb_export_script if enable_mweb else None,
        host=_load_str(local_config, "HOST", default="127.0.0.1"),
        port=_load_int(local_config, "PORT", default=8000),
        api_max_read_bytes=_load_int(local_config, "API_MAX_READ_BYTES", default=524288,
        ),
        index_state_db=_load_required_path(local_config, "INDEX_STATE_DB",
            default=str(get_project_root() / "data" / "index_state.db"),
        ),
        scan_cache_path=_load_required_path(local_config, "SCAN_CACHE_PATH",
            default=str(get_project_root() / "data" / "scan_cache.db"),
        ),
        persist_directory=_load_required_path(local_config, "PERSIST_DIRECTORY",
            default=str(get_project_root() / "data" / "chroma_db"),
        ),
        embedding_cache_path=_load_required_path(local_config, "EMBEDDING_CACHE_PATH",
            default=str(get_project_root() / "data" / "embedding_cache.db"),
        ),
        embedding_model=_load_str(local_config, "EMBEDDING_MODEL", default="text-embedding-v2",
        ),
        embedding_dimensions=_load_optional_int(local_config, "EMBEDDING_DIMENSIONS"),
        embedding_document_text_type=_load_str(local_config, "EMBEDDING_DOCUMENT_TEXT_TYPE", default="document",
        ),
        embedding_query_text_type=_load_str(local_config, "EMBEDDING_QUERY_TEXT_TYPE", default="query",
        ),
        embed_vector_storage_format=_load_str(local_config, "EMBED_VECTOR_STORAGE_FORMAT", default="blob_float32",
        ),
        embed_rate_rps_limit=_load_float(local_config, "EMBED_RATE_RPS_LIMIT", default=28.0,
        ),
        embed_rate_tpm_limit=_load_float(local_config, "EMBED_RATE_TPM_LIMIT", default=1_100_000.0,
        ),
        embed_max_inflight=_load_int(local_config, "EMBED_MAX_INFLIGHT", default=6,
        ),
        embed_retry_max=_load_int(local_config, "EMBED_RETRY_MAX", default=5,
        ),
        embed_backoff_base_ms=_load_int(local_config, "EMBED_BACKOFF_BASE_MS", default=500,
        ),
        embed_backoff_max_ms=_load_int(local_config, "EMBED_BACKOFF_MAX_MS", default=60000,
        ),
        title_path_max_depth=_load_int(local_config, "TITLE_PATH_MAX_DEPTH", default=3,
        ),
        title_path_max_item_chars=_load_int(local_config, "TITLE_PATH_MAX_ITEM_CHARS", default=120,
        ),
        title_path_max_chars=_load_int(local_config, "TITLE_PATH_MAX_CHARS", default=256,
        ),
        skip_aux_chunks_for_short_files=_load_bool(local_config, "SKIP_AUX_CHUNKS_FOR_SHORT_FILES",
            default=False,
        ),
        rebuild_checkpoint_path=_load_required_path(local_config, "REBUILD_CHECKPOINT_PATH",
            default=str(get_project_root() / "data" / "rebuild_checkpoint.db"),
        ),
        rebuild_staging_path=_load_required_path(local_config, "REBUILD_STAGING_PATH",
            default=str(get_project_root() / "data" / "rebuild_staging.db"),
        ),
        index_run_lock_path=_load_required_path(local_config, "INDEX_RUN_LOCK_PATH",
            default=str(get_project_root() / "data" / "index_run.lock"),
        ),
        chunk_size=_load_int(local_config, "CHUNK_SIZE", default=500),
        chunk_overlap=_load_int(local_config, "CHUNK_OVERLAP", default=80),
        max_content_length=_load_int(local_config, "MAX_CONTENT_LENGTH", default=20000,
        ),
        search_timeout_seconds=_load_int(local_config, "SEARCH_TIMEOUT_SECONDS", default=30,
        ),
        search_top_k=_load_int(local_config, "SEARCH_TOP_K", default=250),
        score_threshold=_load_float(local_config, "SCORE_THRESHOLD", default=0.35,
        ),
        index_only_keywords=_load_keyword_tuple(local_config),
        text_extensions=_load_extension_set(local_config, "TEXT_EXTENSIONS", default=frozenset()),
        office_extensions=_load_extension_set(local_config, "OFFICE_EXTENSIONS", default=frozenset()),
        media_extensions=_load_extension_set(local_config, "MEDIA_EXTENSIONS", default=frozenset()),
        supported_extensions=_load_supported_extensions(local_config),
        position_weights=_load_position_weights(local_config),
        keyword_freq_bonus=_load_float(local_config, "KEYWORD_FREQ_BONUS", default=0.03,
        ),
        trust_proxy=_load_bool(local_config, "TRUST_PROXY",
            default=False,
        ),
        sparse_index_path=_load_required_path(local_config, "SPARSE_INDEX_PATH",
            default=str(get_project_root() / "data" / "sparse_index.db"),
        ),
        sparse_top_k=_load_int(local_config, "SPARSE_TOP_K", default=120),
        sparse_filename_weight=_load_float(local_config, "SPARSE_FILENAME_WEIGHT", default=8.0),
        sparse_path_weight=_load_float(local_config, "SPARSE_PATH_WEIGHT", default=3.0),
        sparse_heading_weight=_load_float(local_config, "SPARSE_HEADING_WEIGHT", default=4.0),
        sparse_content_weight=_load_float(local_config, "SPARSE_CONTENT_WEIGHT", default=1.0),
        dense_top_k=_load_int(local_config, "DENSE_TOP_K", default=120),
        fusion_top_k=_load_int(local_config, "FUSION_TOP_K", default=200),
        rrf_k=_load_int(local_config, "RRF_K", default=60),
        rerank_model=_load_str(local_config, "RERANK_MODEL", default="qwen3-rerank"),
        rerank_top_n=_load_int(local_config, "RERANK_TOP_N", default=50),
        rerank_max_doc_chars=_load_int(local_config, "RERANK_MAX_DOC_CHARS", default=2000),
        indexer_batch_size=_load_int(local_config, "INDEXER_BATCH_SIZE", default=50),
        sparse_index_batch_size=_load_int(local_config, "SPARSE_INDEX_BATCH_SIZE", default=5000
        ),
        sparse_checkpoint_interval=_load_int(local_config, "SPARSE_CHECKPOINT_INTERVAL", default=5000
        ),
        sparse_tokenize_workers=_load_int(local_config, "SPARSE_TOKENIZE_WORKERS", default=0
        ),
        sparse_bulk_pragma_fast=_load_bool(local_config, "SPARSE_BULK_PRAGMA_FAST", default=True
        ),
        sparse_skip_fts_delete_on_fresh=_load_bool(local_config, "SPARSE_SKIP_FTS_DELETE_ON_FRESH",
            default=True,
        ),
        embed_max_chars=_load_int(local_config, "EMBED_MAX_CHARS", default=600),
        default_search_limit=_load_int(local_config, "DEFAULT_SEARCH_LIMIT", default=50),
        agg_best_weight=_load_float(local_config, "AGG_BEST_WEIGHT", default=0.70),
        agg_second_weight=_load_float(local_config, "AGG_SECOND_WEIGHT", default=0.15),
        agg_third_weight=_load_float(local_config, "AGG_THIRD_WEIGHT", default=0.05),
        agg_filename_bonus=_load_float(local_config, "AGG_FILENAME_BONUS", default=0.10),
        agg_heading_bonus=_load_float(local_config, "AGG_HEADING_BONUS", default=0.05),
        agg_exact_bonus=_load_float(local_config, "AGG_EXACT_BONUS", default=0.10),
        agg_multi_hit_bonus=_load_float(local_config, "AGG_MULTI_HIT_BONUS", default=0.05),
        agg_large_file_penalty=_load_float(local_config, "AGG_LARGE_FILE_PENALTY", default=0.05),
        agg_recency_bonus_max=_load_float(local_config, "AGG_RECENCY_BONUS_MAX", default=0.05),
        agg_recency_halflife_days=_load_int(local_config, "AGG_RECENCY_HALFLIFE_DAYS", default=7),
        nl_intent_model=_load_str(local_config, "NL_INTENT_MODEL", default="qwen-turbo",
        ),
        search_interpret_model=_load_str(local_config, "SEARCH_INTERPRET_MODEL", default="qwen-turbo",
        ),
        nl_timeout_sec=_load_int(local_config, "NL_TIMEOUT_SEC", default=10,
        ),
        interpret_timeout_sec=_load_int(local_config, "INTERPRET_TIMEOUT_SEC", default=20,
        ),
        nl_max_message_chars=_load_int(local_config, "NL_MAX_MESSAGE_CHARS", default=1000,
        ),
        interpret_max_results=_load_int(local_config, "INTERPRET_MAX_RESULTS", default=10,
        ),
        rate_limit_nl_per_min=_load_int(local_config, "RATE_LIMIT_NL_PER_MIN", default=10,
        ),
        rate_limit_interpret_per_min=_load_int(local_config, "RATE_LIMIT_INTERPRET_PER_MIN", default=10,
        ),
    )
    _validate_settings(settings)
    return settings


def _load_local_config() -> ModuleType | None:
    try:
        return importlib.import_module("config")
    except ModuleNotFoundError:
        return None


def _load_dashscope_api_key(local_config: ModuleType | None) -> str | None:
    if local_config is None:
        return None
    return _normalize_secret(getattr(local_config, "MY_API_KEY", None))


def _normalize_secret(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    if normalized in _PLACEHOLDER_API_KEYS:
        return None
    return normalized or None


def _load_target_dirs(local_config: ModuleType | None) -> tuple[str, ...]:
    if local_config is None:
        return ()
    raw_value = getattr(local_config, "TARGET_DIR", "")
    if isinstance(raw_value, (list, tuple)):
        candidates = list(raw_value)
    elif raw_value:
        candidates = [raw_value]
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


def _load_bool(local_config: ModuleType | None, name: str, *, default: bool) -> bool:
    if local_config is not None and hasattr(local_config, name):
        return bool(getattr(local_config, name))
    return default


def _load_optional_int(local_config: ModuleType | None, name: str) -> int | None:
    if local_config is None or not hasattr(local_config, name):
        return None
    raw_value = getattr(local_config, name)
    if raw_value is None or str(raw_value).strip() == "":
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise InvalidSettingError(f"{name} 不是合法整数: {raw_value}") from exc


def _load_int(local_config: ModuleType | None, name: str, *, default: int) -> int:
    if local_config is None or not hasattr(local_config, name):
        return default
    raw_value = getattr(local_config, name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise InvalidSettingError(f"{name} 不是合法整数: {raw_value}") from exc


def _load_float(local_config: ModuleType | None, name: str, *, default: float) -> float:
    if local_config is None or not hasattr(local_config, name):
        return default
    raw_value = getattr(local_config, name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except (TypeError, ValueError) as exc:
        raise InvalidSettingError(f"{name} 不是合法数字: {raw_value}") from exc


def _load_str(local_config: ModuleType | None, name: str, *, default: str) -> str:
    if local_config is None or not hasattr(local_config, name):
        return default
    raw_value = getattr(local_config, name)
    if raw_value is None:
        return default
    normalized = str(raw_value).strip()
    return normalized or default


def _load_optional_path(local_config: ModuleType | None, name: str) -> str | None:
    if local_config is None or not hasattr(local_config, name):
        return None
    return _normalize_path(getattr(local_config, name))


def _load_required_path(
    local_config: ModuleType | None,
    name: str,
    *,
    default: str,
) -> str:
    raw_value = None
    if local_config is not None and hasattr(local_config, name):
        raw_value = getattr(local_config, name)
    normalized = _normalize_path(raw_value)
    return normalized or _normalize_path(default) or default


def _normalize_path(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    return str(Path(text).expanduser().resolve())


def _load_keyword_tuple(local_config: ModuleType | None) -> tuple[str, ...]:
    if local_config is None:
        return ()
    raw_value = getattr(local_config, "INDEX_ONLY_KEYWORDS", ())
    if not isinstance(raw_value, (list, tuple, set, frozenset)):
        raise InvalidSettingError("INDEX_ONLY_KEYWORDS 必须是序列类型")
    return tuple(str(item) for item in raw_value if str(item).strip())


def _load_extension_set(
    local_config: ModuleType | None,
    name: str,
    *,
    default: frozenset[str],
) -> frozenset[str]:
    if local_config is None or not hasattr(local_config, name):
        return default
    raw_value = getattr(local_config, name)
    if not isinstance(raw_value, (set, frozenset, list, tuple)):
        raise InvalidSettingError(f"{name} 必须是集合或序列类型")
    return frozenset(str(item) for item in raw_value)


def _load_supported_extensions(local_config: ModuleType | None) -> frozenset[str]:
    if local_config is not None and hasattr(local_config, "SUPPORTED_EXTENSIONS"):
        raw_value = getattr(local_config, "SUPPORTED_EXTENSIONS")
        if not isinstance(raw_value, (set, frozenset, list, tuple)):
            raise InvalidSettingError("SUPPORTED_EXTENSIONS 必须是集合或序列类型")
        return frozenset(str(item) for item in raw_value)
    text_extensions = _load_extension_set(local_config, "TEXT_EXTENSIONS", default=frozenset())
    office_extensions = _load_extension_set(local_config, "OFFICE_EXTENSIONS", default=frozenset())
    media_extensions = _load_extension_set(local_config, "MEDIA_EXTENSIONS", default=frozenset())
    return text_extensions | office_extensions | media_extensions


def _load_position_weights(local_config: ModuleType | None) -> MappingProxyType:
    raw_value = getattr(local_config, "POSITION_WEIGHTS", None) if local_config is not None else None
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
    if settings.embedding_dimensions is not None and settings.embedding_dimensions <= 0:
        raise InvalidSettingError("EMBEDDING_DIMENSIONS 必须大于 0")
    if settings.embed_vector_storage_format != "blob_float32":
        raise InvalidSettingError(
            "EMBED_VECTOR_STORAGE_FORMAT 当前仅支持 blob_float32（float16 尚未启用）"
        )
    if settings.embed_rate_rps_limit <= 0:
        raise InvalidSettingError("EMBED_RATE_RPS_LIMIT 必须大于 0")
    if settings.embed_rate_tpm_limit <= 0:
        raise InvalidSettingError("EMBED_RATE_TPM_LIMIT 必须大于 0")
    if settings.embed_max_inflight <= 0:
        raise InvalidSettingError("EMBED_MAX_INFLIGHT 必须大于 0")
    if settings.embed_retry_max < 0:
        raise InvalidSettingError("EMBED_RETRY_MAX 必须大于等于 0")
    if settings.embed_backoff_base_ms <= 0:
        raise InvalidSettingError("EMBED_BACKOFF_BASE_MS 必须大于 0")
    if settings.embed_backoff_max_ms < settings.embed_backoff_base_ms:
        raise InvalidSettingError("EMBED_BACKOFF_MAX_MS 必须大于等于 EMBED_BACKOFF_BASE_MS")
    if settings.title_path_max_depth <= 0:
        raise InvalidSettingError("TITLE_PATH_MAX_DEPTH 必须大于 0")
    if settings.title_path_max_item_chars <= 0:
        raise InvalidSettingError("TITLE_PATH_MAX_ITEM_CHARS 必须大于 0")
    if settings.title_path_max_chars <= 0:
        raise InvalidSettingError("TITLE_PATH_MAX_CHARS 必须大于 0")
    if settings.sparse_index_batch_size <= 0:
        raise InvalidSettingError("SPARSE_INDEX_BATCH_SIZE 必须大于 0")
    if settings.sparse_checkpoint_interval <= 0:
        raise InvalidSettingError("SPARSE_CHECKPOINT_INTERVAL 必须大于 0")
    if settings.sparse_tokenize_workers < 0:
        raise InvalidSettingError("SPARSE_TOKENIZE_WORKERS 必须大于等于 0")
