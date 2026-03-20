import os
import mimetypes
import subprocess
import logging
from flask import Flask, request, jsonify, render_template, send_file

import config

logger = logging.getLogger(__name__)
from search import search_core

app = Flask(__name__)


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


@app.route("/")
def index():
    enable_mweb = bool(getattr(config, "ENABLE_MWEB", True))
    return render_template("index.html", enable_mweb=enable_mweb)


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


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")
    port = int(os.environ.get("PORT", getattr(config, "PORT", 8000)))
    host = os.environ.get("FLASK_HOST", getattr(config, "HOST", "127.0.0.1"))
    app.run(host=host, port=port, debug=debug)
