import argparse
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
import logging
import threading
import time
import hashlib
from typing import Callable, TypeVar
import chromadb
from chromadb.errors import NotFoundError, InternalError
from langchain_chroma import Chroma
from langchain_core.documents import Document

from .embedding_cache import CachedEmbeddings
from .infra.settings import (
    Settings,
    apply_sdk_environment,
    get_settings,
    require_dashscope_api_key,
)

logger = logging.getLogger(__name__)

_embeddings = None
_vectordb = None
_chroma_client = None
_search_executor: ThreadPoolExecutor | None = None
_search_executor_lock = threading.Lock()
_search_execution_slot = threading.BoundedSemaphore(value=1)

# ================= 搜索缓存 =================
_search_cache: dict[str, tuple[list[dict], float]] = {}
_cache_lock = threading.Lock()
CACHE_TTL_SECONDS = 1200  # 20分钟缓存
MAX_CACHE_SIZE = 100  # 最大缓存条目数
_TimeoutResultT = TypeVar("_TimeoutResultT")


def _get_cache_key(
    query: str,
    source_filter: str | None,
    date_field: str | None,
    date_from: float | None,
    date_to: float | None,
    *,
    exact_focus: bool = False,
) -> str:
    """生成缓存键"""
    index_token = _get_index_cache_token()
    key_data = (
        f"{query}:{source_filter}:{date_field}:{date_from}:{date_to}:"
        f"ef={exact_focus}:idx={index_token}"
    )
    return hashlib.sha256(key_data.encode()).hexdigest()


def _get_index_cache_token(settings: Settings | None = None) -> str:
    """返回当前索引版本标记，用于在外部重建索引后自动失效搜索缓存。"""
    effective_settings = settings or get_settings()
    persist_directory = getattr(effective_settings, "persist_directory", None)
    if not persist_directory:
        return "unknown"
    db_path = Path(persist_directory) / "chroma.sqlite3"
    try:
        stat = db_path.stat()
    except OSError:
        return "missing"
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _get_cached_search(cache_key: str) -> list[dict] | None:
    """获取缓存的搜索结果，TTL = 20分钟"""
    with _cache_lock:
        if cache_key in _search_cache:
            result, timestamp = _search_cache[cache_key]
            if time.time() - timestamp < CACHE_TTL_SECONDS:
                logger.debug(f"缓存命中: {cache_key[:8]}...")
                return result
            else:
                del _search_cache[cache_key]
        return None


def _set_cached_search(cache_key: str, result: list[dict]):
    """缓存搜索结果，限制缓存大小"""
    with _cache_lock:
        # 限制缓存大小
        if len(_search_cache) >= MAX_CACHE_SIZE:
            # 删除最旧的条目
            oldest_key = min(_search_cache, key=lambda k: _search_cache[k][1])
            del _search_cache[oldest_key]
            logger.debug(f"缓存清理: 移除最旧条目 {oldest_key[:8]}...")
        _search_cache[cache_key] = (result, time.time())


def clear_search_cache():
    """清空搜索缓存（用于索引更新后）"""
    with _cache_lock:
        _search_cache.clear()
        logger.info("搜索缓存已清空")


def get_search_cache_size() -> int:
    """返回当前搜索缓存条目数。"""
    with _cache_lock:
        return len(_search_cache)


def get_search_cache_max_size() -> int:
    """返回搜索缓存最大容量。"""
    return MAX_CACHE_SIZE


# ================= 超时控制 =================
class SearchTimeoutError(Exception):
    """搜索执行超时。"""


class SearchExecutionBusyError(Exception):
    """搜索执行器仍忙，当前请求未进入执行。"""


def _get_search_executor() -> ThreadPoolExecutor:
    """返回共享搜索执行器，避免每次请求创建新线程池。"""
    global _search_executor
    with _search_executor_lock:
        if _search_executor is None:
            _search_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="everythingsearch-search",
            )
    return _search_executor


def _acquire_search_execution_slot() -> None:
    """尝试获取单飞执行槽位。"""
    if not _search_execution_slot.acquire(blocking=False):
        raise SearchExecutionBusyError("搜索执行繁忙，请稍后重试")


def _release_search_execution_slot(_future=None) -> None:
    """释放单飞执行槽位。"""
    try:
        _search_execution_slot.release()
    except ValueError:
        logger.debug("搜索执行槽位已处于空闲状态，忽略重复释放")


def _reset_search_executor_state_for_tests() -> None:
    """重置搜索执行器状态，仅供测试使用。"""
    global _search_executor, _search_execution_slot
    with _search_executor_lock:
        executor = _search_executor
        _search_executor = None
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)
    _search_execution_slot = threading.BoundedSemaphore(value=1)


def _run_with_timeout(
    func: Callable[[], _TimeoutResultT],
    timeout_seconds: int | float,
) -> _TimeoutResultT:
    """在独立线程中执行函数，并在超时时抛出显式异常。``timeout_seconds <= 0`` 时仅关闭超时，不关闭单飞保护。"""
    _acquire_search_execution_slot()

    if timeout_seconds <= 0:
        try:
            return func()
        finally:
            _release_search_execution_slot()

    executor = _get_search_executor()
    try:
        future = executor.submit(func)
    except Exception:
        _release_search_execution_slot()
        raise
    future.add_done_callback(_release_search_execution_slot)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        raise SearchTimeoutError(f"搜索操作超时（>{timeout_seconds}s）") from exc


def _get_vectordb():
    """Get vectordb, clearing cache if collection was rebuilt (NotFoundError)."""
    global _embeddings, _vectordb, _chroma_client
    if _vectordb is None:
        settings = get_settings()
        require_dashscope_api_key(settings)
        apply_sdk_environment(settings)
        _chroma_client = chromadb.PersistentClient(path=settings.persist_directory)
        _embeddings = CachedEmbeddings(
            model=settings.embedding_model,
            cache_path=settings.embedding_cache_path,
        )
        _vectordb = Chroma(
            client=_chroma_client,
            embedding_function=_embeddings,
            collection_name="local_files",
        )
    return _vectordb


def _get_chroma_collection():
    """Get ChromaDB collection, reusing the shared client."""
    try:
        return _get_vectordb()._collection
    except (NotFoundError, InternalError):
        return None


def _clear_vectordb_cache():
    """Clear cached vectordb (e.g. after index rebuild)."""
    global _embeddings, _vectordb, _chroma_client
    if _chroma_client is not None:
        try:
            _chroma_client.clear_system_cache()
            _chroma_client.close()
        except Exception as exc:
            logger.debug("清理 ChromaDB 客户端缓存失败: %s", exc)
    _embeddings = None
    _vectordb = None
    _chroma_client = None
    # 同时清空搜索缓存
    clear_search_cache()


def _apply_weights(
    results: list[tuple[Document, float]],
    query: str,
    settings: Settings | None = None,
) -> list[tuple[Document, float]]:
    """Apply position-based weight and keyword frequency bonus to raw scores."""
    effective_settings = settings or get_settings()
    weighted = []
    query_lower = query.lower()
    for doc, score in results:
        chunk_type = doc.metadata.get("chunk_type", "content")
        factor = effective_settings.position_weights.get(chunk_type, 1.0)

        freq = doc.page_content.lower().count(query_lower)
        if freq > 1:
            freq_factor = max(0.85, 1.0 - effective_settings.keyword_freq_bonus * (freq - 1))
            factor *= freq_factor

        weighted.append((doc, score * factor))
    return weighted


def _dedup_by_file(results: list[tuple[Document, float]], threshold: float) -> dict[str, tuple[Document, float]]:
    best: dict[str, tuple[Document, float]] = {}
    for doc, score in results:
        if score > threshold:
            continue
        source = doc.metadata.get("source", "")
        if source not in best or score < best[source][1]:
            best[source] = (doc, score)
    return best


def _keyword_fallback(
    query: str,
    settings: Settings | None = None,
    where_filter: dict | None = None,
) -> dict[str, tuple[Document, float]]:
    """Keyword exact-match fallback, reusing shared Chroma client."""
    effective_settings = settings or get_settings()
    col = _get_chroma_collection()
    if col is None:
        return {}
    try:
        tokens = [t for t in query.strip().split() if t]
        tokens = list(dict.fromkeys(tokens)) or [query]
        if len(tokens) == 1:
            where_doc = {"$contains": tokens[0]}
        else:
            where_doc = {"$or": [{"$contains": t} for t in tokens]}

        hits = col.get(
            where_document=where_doc,
            where=where_filter,
            include=["documents", "metadatas"],
            limit=effective_settings.search_top_k,
        )
    except Exception as e:
        logger.debug("Keyword fallback failed: %s", e)
        return {}

    base_score = 0.10
    query_lower = query.lower()
    best: dict[str, tuple[Document, float]] = {}
    for i in range(len(hits["ids"])):
        meta = hits["metadatas"][i] or {}
        source = meta.get("source", "")
        doc = Document(page_content=hits["documents"][i], metadata=meta)

        chunk_type = meta.get("chunk_type", "content")
        pos_factor = effective_settings.position_weights.get(chunk_type, 1.0)
        freq = doc.page_content.lower().count(query_lower)
        freq_factor = (
            max(0.85, 1.0 - effective_settings.keyword_freq_bonus * (freq - 1))
            if freq > 1
            else 1.0
        )
        adjusted = base_score * pos_factor * freq_factor

        if source not in best or adjusted < best[source][1]:
            best[source] = (doc, adjusted)
    return best


def _build_where_filter(
    source_filter: str | None,
    date_field: str | None,
    date_from: float | None,
    date_to: float | None,
) -> dict | None:
    """Build a ChromaDB ``where`` filter combining source type and time range."""
    clauses: list[dict] = []

    if source_filter and source_filter != "all":
        clauses.append({"source_type": source_filter})

    field = date_field if date_field in ("mtime", "ctime") else "mtime"
    if date_from is not None:
        clauses.append({field: {"$gte": date_from}})
    if date_to is not None:
        clauses.append({field: {"$lte": date_to}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _ranked_pairs_to_results(ranked: list[tuple[Document, float]], query: str) -> list[dict]:
    """将 (Document, score) 列表格式化为 API / UI 使用的结果行。"""
    results: list[dict] = []
    for doc, score in ranked:
        source_type = doc.metadata.get("source_type", "file")

        filename = doc.metadata.get("filename") or "未知文件"
        filepath = doc.metadata.get("source") or ""
        filetype = doc.metadata.get("type") or ""
        raw_cat = doc.metadata.get("categories")
        categories = ", ".join(raw_cat) if isinstance(raw_cat, (list, tuple)) else (raw_cat or "")

        if score <= 0.10:
            tag = "精确匹配"
            relevance = "关键词命中"
        else:
            tag = "语义匹配"
            relevance = f"{max(0, (1 - score)) * 100:.0f}%"

        raw = doc.page_content.strip().replace("\n", " ")
        preview = raw
        if raw and query.strip():
            q = query.strip().lower()
            idx = raw.lower().find(q)
            if idx == -1:
                for t in query.split():
                    t = t.strip()
                    if not t:
                        continue
                    idx = raw.lower().find(t.lower())
                    if idx != -1:
                        break
            if idx != -1:
                start = max(0, idx - 60)
                end = min(len(raw), idx + len(q) + 120)
                preview = ("…" if start > 0 else "") + raw[start:end]
                if end < len(raw):
                    preview += "…"
        if len(preview) > 220:
            preview = preview[:220] + "…"

        mtime = doc.metadata.get("mtime", 0)
        if mtime is not None and not isinstance(mtime, (int, float)):
            mtime = 0
        ctime = doc.metadata.get("ctime", 0)
        if ctime is not None and not isinstance(ctime, (int, float)):
            ctime = 0

        results.append(
            {
                "filename": filename,
                "filepath": filepath,
                "relevance": relevance,
                "tag": tag,
                "preview": preview,
                "filetype": filetype,
                "mtime": mtime,
                "ctime": ctime,
                "source_type": source_type,
                "categories": categories,
            }
        )
    return results


def _do_search_core(
    query: str,
    source_filter: str | None = None,
    date_field: str | None = None,
    date_from: float | None = None,
    date_to: float | None = None,
    *,
    exact_focus: bool = False,
) -> list[dict]:
    """
    实际的搜索核心逻辑（内部使用，支持超时控制）
    """
    settings = get_settings()
    where_filter = _build_where_filter(source_filter, date_field, date_from, date_to)

    keyword_only = exact_focus
    if keyword_only:
        kw_hits = _keyword_fallback(query, settings, where_filter=where_filter)
        if not kw_hits:
            keyword_only = False
    if keyword_only:
        ranked_kw = sorted(kw_hits.values(), key=lambda x: x[1])
        filtered_kw: list[tuple[Document, float]] = []
        for doc, kw_score in ranked_kw:
            source_type = doc.metadata.get("source_type", "file")
            if source_filter and source_filter != "all":
                if source_type != source_filter:
                    continue
            filtered_kw.append((doc, kw_score))
        if filtered_kw:
            return _ranked_pairs_to_results(filtered_kw, query)
        # 有关键词命中但被来源等条件筛空时，回退混合检索以免误返回空结果
        keyword_only = False

    def _do_search():
        vectordb = _get_vectordb()
        k = settings.search_top_k
        if where_filter:
            return vectordb.similarity_search_with_score(
                query, k=k, filter=where_filter)
        return vectordb.similarity_search_with_score(query, k=k * 2)

    try:
        vector_results = _do_search()
    except (NotFoundError, InternalError):
        _clear_vectordb_cache()
        try:
            vector_results = _do_search()
        except (NotFoundError, InternalError):
            return []

    weighted_results = _apply_weights(vector_results, query, settings)
    best_by_file = _dedup_by_file(weighted_results, settings.score_threshold)

    keyword_hits = _keyword_fallback(query, settings, where_filter=where_filter)
    for source, (doc, score) in keyword_hits.items():
        if source not in best_by_file:
            best_by_file[source] = (doc, score)

    ranked = sorted(best_by_file.values(), key=lambda x: x[1])
    filtered: list[tuple[Document, float]] = []
    for doc, score in ranked:
        source_type = doc.metadata.get("source_type", "file")
        if source_filter and source_filter != "all":
            if source_type != source_filter:
                continue
        filtered.append((doc, score))
    return _ranked_pairs_to_results(filtered, query)


def search_core(
    query: str,
    source_filter: str | None = None,
    date_field: str | None = None,
    date_from: float | None = None,
    date_to: float | None = None,
    *,
    exact_focus: bool = False,
) -> list[dict]:
    """
    Core search: returns a list of result dicts, sorted by relevance.
    添加缓存与超时控制；超时秒数由 SEARCH_TIMEOUT_SECONDS 配置，默认 30 秒。
    
    Each dict: {filename, filepath, relevance, tag, preview, filetype, mtime, ctime, source_type, categories}

    source_filter: None/"all" = everything, "file" = files only, "mweb" = MWeb notes only
    date_field: "mtime" or "ctime" (default "mtime")
    date_from / date_to: unix timestamps for time-range filtering (inclusive)
    exact_focus: 为 True 时仅使用关键词倒排路径（无命中时自动回退为向量+关键词混合）。
    """
    # 1. 检查缓存
    cache_key = _get_cache_key(
        query, source_filter, date_field, date_from, date_to, exact_focus=exact_focus
    )
    cached = _get_cached_search(cache_key)
    if cached is not None:
        return cached

    settings = get_settings()

    def _execute_search() -> list[dict]:
        return _do_search_core(
            query,
            source_filter,
            date_field,
            date_from,
            date_to,
            exact_focus=exact_focus,
        )

    try:
        results = _run_with_timeout(_execute_search, settings.search_timeout_seconds)
        _set_cached_search(cache_key, results)
        return results
    except SearchTimeoutError:
        logger.warning(
            "搜索超时 (>%ss): query='%s'",
            settings.search_timeout_seconds,
            query[:50],
        )
        raise


# ---- CLI ----
def _print_results(query: str, results: list[dict]):
    if not results:
        print("🤔 未找到相关内容。试试换个描述方式？")
        return
    print(f"# 🔍 搜索结果: {query}\n")
    for i, r in enumerate(results):
        print(f"## {i + 1}. {r['filename']}")
        print(f"> 📄 **路径**: `{r['filepath']}`")
        print(f"> 🎯 **相关度**: {r['relevance']} ({r['tag']})")
        print(f"\n{r['preview']}\n")
        print("---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('query', type=str, nargs='?')
    args = parser.parse_args()
    if args.query:
        _print_results(args.query, search_core(args.query))
    else:
        print("请输入搜索关键词。")
