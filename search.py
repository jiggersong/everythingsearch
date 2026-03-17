import os
import argparse
import logging
import config
import chromadb
from chromadb.errors import NotFoundError, InternalError
from langchain_chroma import Chroma
from langchain_core.documents import Document

from embedding_cache import CachedEmbeddings

logger = logging.getLogger(__name__)

_embeddings = None
_vectordb = None
_chroma_client = None


def _ensure_dashscope_api_key():
    """Ensure DashScope API key exists in environment (used by langchain)."""
    if os.environ.get("DASHSCOPE_API_KEY"):
        return
    if getattr(config, "MY_API_KEY", ""):
        os.environ["DASHSCOPE_API_KEY"] = config.MY_API_KEY
        return
    raise RuntimeError(
        "未配置 DashScope API Key。请在环境变量 DASHSCOPE_API_KEY 或 config.py 的 MY_API_KEY 中设置。"
    )


def _get_vectordb():
    """Get vectordb, clearing cache if collection was rebuilt (NotFoundError)."""
    global _embeddings, _vectordb, _chroma_client
    if _vectordb is None:
        _ensure_dashscope_api_key()
        _chroma_client = chromadb.PersistentClient(path=config.PERSIST_DIRECTORY)
        _embeddings = CachedEmbeddings(
            model=config.EMBEDDING_MODEL,
            cache_path=config.EMBEDDING_CACHE_PATH,
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
        except Exception:
            pass
    _embeddings = None
    _vectordb = None
    _chroma_client = None


def _apply_weights(
    results: list[tuple[Document, float]], query: str
) -> list[tuple[Document, float]]:
    """Apply position-based weight and keyword frequency bonus to raw scores."""
    weighted = []
    query_lower = query.lower()
    for doc, score in results:
        chunk_type = doc.metadata.get("chunk_type", "content")
        factor = config.POSITION_WEIGHTS.get(chunk_type, 1.0)

        freq = doc.page_content.lower().count(query_lower)
        if freq > 1:
            freq_factor = max(0.85, 1.0 - config.KEYWORD_FREQ_BONUS * (freq - 1))
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
    where_filter: dict | None = None,
) -> dict[str, tuple[Document, float]]:
    """Keyword exact-match fallback, reusing shared Chroma client."""
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
            limit=config.SEARCH_TOP_K,
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
        pos_factor = config.POSITION_WEIGHTS.get(chunk_type, 1.0)
        freq = doc.page_content.lower().count(query_lower)
        freq_factor = max(0.85, 1.0 - config.KEYWORD_FREQ_BONUS * (freq - 1)) if freq > 1 else 1.0
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


def search_core(
    query: str,
    source_filter: str | None = None,
    date_field: str | None = None,
    date_from: float | None = None,
    date_to: float | None = None,
) -> list[dict]:
    """
    Core search: returns a list of result dicts, sorted by relevance.
    Each dict: {filename, filepath, relevance, tag, preview, filetype, mtime, ctime, source_type, categories}

    source_filter: None/"all" = everything, "file" = files only, "mweb" = MWeb notes only
    date_field: "mtime" or "ctime" (default "mtime")
    date_from / date_to: unix timestamps for time-range filtering (inclusive)
    """
    where_filter = _build_where_filter(source_filter, date_field, date_from, date_to)

    def _do_search():
        vectordb = _get_vectordb()
        k = config.SEARCH_TOP_K
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

    weighted_results = _apply_weights(vector_results, query)
    best_by_file = _dedup_by_file(weighted_results, config.SCORE_THRESHOLD)

    keyword_hits = _keyword_fallback(query, where_filter=where_filter)
    for source, (doc, score) in keyword_hits.items():
        if source not in best_by_file:
            best_by_file[source] = (doc, score)

    ranked = sorted(best_by_file.values(), key=lambda x: x[1])
    results = []
    for doc, score in ranked:
        source_type = doc.metadata.get("source_type", "file")

        if source_filter and source_filter != "all":
            if source_type != source_filter:
                continue

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

        raw = doc.page_content.strip().replace('\n', ' ')
        # 尝试截取靠近命中关键词的位置，预览更聚焦
        preview = raw
        if raw and query.strip():
            q = query.strip().lower()
            idx = raw.lower().find(q)
            if idx == -1:
                # 如果整句找不到，就按空格拆分后找第一个 token
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

        results.append({
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
        })
    return results


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
