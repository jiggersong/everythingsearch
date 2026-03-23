import os
import mimetypes
import subprocess
import logging
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file

import config

logger = logging.getLogger(__name__)
from .search import search_core, clear_search_cache, _search_cache

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(_PKG_DIR, "templates"),
    static_folder=os.path.join(_PKG_DIR, "static"),
)

# 全局状态
_warmup_done = False
_start_time = time.time()


def _warmup_vectordb():
    """预热向量数据库连接"""
    global _warmup_done
    if _warmup_done:
        return True
    try:
        # 触发向量数据库初始化
        from .search import _get_vectordb
        _ = _get_vectordb()
        _warmup_done = True
        logger.info("向量数据库预热完成")
        return True
    except Exception as e:
        logger.warning(f"预热失败: {e}")
        return False


def _safe_filepath(filepath: str) -> bool:
    """Validate filepath: must exist, be a file, and not contain path traversal."""
    if not filepath:
        return False
    if ".." in os.path.normpath(filepath).split(os.sep):
        return False
    path = os.path.abspath(os.path.realpath(filepath))
    return os.path.isfile(path)


def _get_allowed_index_roots() -> list[str]:
    """Directories that are indexed (and thus allowed for read/download APIs)."""
    roots: list[str] = []
    if hasattr(config, "get_target_dirs"):
        raw = config.get_target_dirs()
    else:
        t = getattr(config, "TARGET_DIR", "")
        if isinstance(t, (list, tuple)):
            raw = [str(x) for x in t if x]
        else:
            raw = [str(t)] if t else []
    for d in raw:
        if not d:
            continue
        try:
            roots.append(os.path.abspath(os.path.realpath(d)))
        except OSError:
            continue
    if getattr(config, "ENABLE_MWEB", False):
        md = getattr(config, "MWEB_DIR", "") or ""
        if md:
            try:
                rp = os.path.abspath(os.path.realpath(md))
                if os.path.isdir(rp):
                    roots.append(rp)
            except OSError:
                pass
    return roots


def _is_under_index_roots(filepath: str) -> bool:
    """True if filepath is an existing file whose real path lies under an indexed root."""
    if not filepath:
        return False
    if ".." in os.path.normpath(filepath).split(os.sep):
        return False
    try:
        path = os.path.abspath(os.path.realpath(filepath))
    except OSError:
        return False
    if not os.path.isfile(path):
        return False
    for root in _get_allowed_index_roots():
        if path == root or path.startswith(root + os.sep):
            return True
    return False


@app.before_request
def before_request():
    """每个请求前的处理：确保预热完成"""
    if not _warmup_done:
        _warmup_vectordb()


@app.route("/")
def index():
    enable_mweb = bool(getattr(config, "ENABLE_MWEB", True))
    return render_template("index.html", enable_mweb=enable_mweb)


@app.route("/api/health")
def api_health():
    """健康检查接口，返回系统状态"""
    # 检查向量数据库
    vdb_status = "ok"
    doc_count = 0
    try:
        from .search import _get_chroma_collection
        col = _get_chroma_collection()
        if col:
            doc_count = col.count()
        else:
            vdb_status = "not_initialized"
    except Exception as e:
        vdb_status = f"error: {str(e)}"
    
    # 计算运行时间
    uptime_seconds = int(time.time() - _start_time)
    uptime_str = f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m {uptime_seconds % 60}s"
    
    # 缓存统计
    cache_stats = {
        "cached_queries": len(_search_cache),
        "max_cache_size": 100
    }
    
    return jsonify({
        "ok": True,
        "status": "healthy" if vdb_status == "ok" else "degraded",
        "version": "1.0.0",
        "uptime": uptime_str,
        "uptime_seconds": uptime_seconds,
        "vectordb": {
            "status": vdb_status,
            "document_count": doc_count
        },
        "cache": cache_stats,
        "timestamp": datetime.now().isoformat()
    })


@app.route("/api/cache/clear", methods=["POST"])
def api_clear_cache():
    """清空搜索缓存（索引更新后调用）"""
    clear_search_cache()
    return jsonify({"ok": True, "message": "搜索缓存已清空"})


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    source = request.args.get("source", "all").strip()
    enable_mweb = bool(getattr(config, "ENABLE_MWEB", True))
    if not enable_mweb and source == "mweb":
        return jsonify({
            "results": [],
            "query": query,
            "error": "当前实例已关闭 MWeb 数据源（ENABLE_MWEB=False）",
        }), 400
    if not enable_mweb and source == "all":
        source = "file"
    date_field = request.args.get("date_field", "mtime").strip()
    raw_from = request.args.get("date_from", "").strip()
    raw_to = request.args.get("date_to", "").strip()
    date_from = float(raw_from) if raw_from else None
    date_to = float(raw_to) if raw_to else None

    if not query:
        return jsonify({"results": [], "query": ""})
    try:
        results = search_core(
            query,
            source_filter=source,
            date_field=date_field,
            date_from=date_from,
            date_to=date_to,
        )
        limit = request.args.get("limit", type=int)
        if limit is not None:
            limit = max(1, min(limit, 200))
            results = results[:limit]
        return jsonify({"results": results, "query": query})
    except Exception as e:
        logger.exception("搜索失败: %s", e)
        return jsonify({
            "results": [],
            "query": query,
            "error": str(e),
        }), 500


@app.route("/api/reveal", methods=["POST"])
def api_reveal():
    """Reveal a file in macOS Finder."""
    filepath = request.json.get("filepath", "")
    if not _safe_filepath(filepath):
        return jsonify({"ok": False, "error": "文件不存在或路径无效"}), 404
    subprocess.Popen(["open", "-R", filepath])
    return jsonify({"ok": True})


@app.route("/api/open", methods=["POST"])
def api_open():
    """Open a file with default application (macOS)."""
    filepath = request.json.get("filepath", "")
    if not _safe_filepath(filepath):
        return jsonify({"ok": False, "error": "文件不存在或路径无效"}), 404
    subprocess.Popen(["open", filepath])
    return jsonify({"ok": True})


@app.route("/api/file/read", methods=["GET"])
def api_file_read():
    """
    Read a text preview of a file under indexed directories (for agents / skills).
    Query: filepath (required), max_bytes (optional, capped by config API_MAX_READ_BYTES).
    """
    filepath = request.args.get("filepath", "").strip()
    if not _is_under_index_roots(filepath):
        return jsonify({"ok": False, "error": "文件不存在或不在已索引目录内"}), 404
    max_b = request.args.get("max_bytes", type=int)
    cap = int(getattr(config, "API_MAX_READ_BYTES", 524288))
    if max_b is None or max_b < 1:
        max_b = cap
    else:
        max_b = min(max_b, cap)
    real_fp = os.path.realpath(filepath)
    try:
        with open(real_fp, "rb") as f:
            raw = f.read(max_b + 1)
    except OSError as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    truncated = len(raw) > max_b
    raw = raw[:max_b]
    if b"\x00" in raw[:8192]:
        return jsonify({
            "ok": False,
            "error": "该文件为二进制或无法作为文本安全展示，请使用 /api/file/download",
            "filepath": filepath,
        }), 400
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    st = os.stat(real_fp)
    return jsonify({
        "ok": True,
        "filepath": real_fp,
        "size": st.st_size,
        "truncated": truncated,
        "content": text,
    })


@app.route("/api/file/download", methods=["GET"])
def api_file_download():
    """Download a file under indexed directories (Content-Disposition: attachment)."""
    filepath = request.args.get("filepath", "").strip()
    if not _is_under_index_roots(filepath):
        return jsonify({"ok": False, "error": "文件不存在或不在已索引目录内"}), 404
    basename = os.path.basename(filepath)
    mtype, _ = mimetypes.guess_type(basename)
    return send_file(
        os.path.realpath(filepath),
        as_attachment=True,
        download_name=basename,
        mimetype=mtype or "application/octet-stream",
    )


def main():
    """CLI entry: python -m everythingsearch.app"""
    logger.info("启动 EverythingSearch 服务...")
    _warmup_vectordb()

    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")
    port = int(os.environ.get("PORT", getattr(config, "PORT", 8000)))
    host = os.environ.get("FLASK_HOST", getattr(config, "HOST", "127.0.0.1"))
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
