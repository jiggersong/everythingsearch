import os
import logging
from dataclasses import asdict
from flask import Flask, request, jsonify, render_template, send_file

from .file_access import (
    FileAuthorizationError,
    InvalidPathError,
    TargetFileNotFoundError,
    UnauthorizedFileError,
)
from .infra.settings import get_settings
from .logging_config import setup_flask_dev_daily_file_logging
from .request_validation import (
    RequestValidationError,
    map_validation_error,
    parse_file_body_request,
    parse_file_query_request,
    parse_json_object_body,
    parse_search_request,
)
from .services.file_service import BinaryPreviewNotAllowedError, FileService
from .services.health_service import HealthService
from .services.search_service import (
    SearchExecutionBusyServiceError,
    SearchExecutionTimeoutError,
    SearchService,
    SearchSourceNotAvailableError,
)
from .infra.rate_limiting import rate_limit
from .services.nl_search_service import NLSearchService, NLSearchServiceError
from .services.search_interpret_service import SearchInterpretService, SearchInterpretServiceError
from flask import Response, stream_with_context

logger = logging.getLogger(__name__)

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
file_service = FileService()
search_service = SearchService()
health_service = HealthService(search_service=search_service)
nl_search_service = NLSearchService()
search_interpret_service = SearchInterpretService()

app = Flask(
    __name__,
    template_folder=os.path.join(_PKG_DIR, "templates"),
    static_folder=os.path.join(_PKG_DIR, "static"),
)

def _map_file_access_error(exc: Exception) -> tuple[dict, int]:
    """将文件访问相关异常映射为稳定的 HTTP 响应。"""
    if isinstance(exc, InvalidPathError):
        logger.info("文件访问请求路径无效: %s", exc)
        return {"ok": False, "error": "路径参数无效"}, 400
    if isinstance(exc, UnauthorizedFileError):
        logger.warning("拒绝未授权文件访问: %s", exc)
        return {"ok": False, "error": "文件不存在或不在已索引目录内"}, 404
    if isinstance(exc, TargetFileNotFoundError):
        return {"ok": False, "error": "文件不存在或不在已索引目录内"}, 404
    logger.error("文件访问失败: %s", exc, exc_info=True)
    return {"ok": False, "error": "文件访问失败"}, 500


@app.before_request
def before_request():
    """每个请求前的处理：确保预热完成"""
    health_service.ensure_warmup()


@app.route("/")
def index():
    settings = get_settings()
    return render_template(
        "index.html",
        enable_mweb=settings.enable_mweb,
        smart_search_available=bool(settings.dashscope_api_key),
    )


@app.route("/api/health")
def api_health():
    """健康检查接口，返回系统状态"""
    snapshot = health_service.get_health_snapshot()
    return jsonify(asdict(snapshot))


@app.route("/api/search")
def api_search():
    try:
        parsed_request = parse_search_request(request)
    except RequestValidationError as exc:
        error_message, status = map_validation_error(exc)
        return jsonify({
            "results": [],
            "query": (request.args.get("q", "") or "").strip(),
            "error": error_message,
        }), status

    try:
        result = search_service.search(parsed_request)
        return jsonify({"results": result.results, "query": result.query})
    except SearchSourceNotAvailableError as exc:
        return jsonify({
            "results": [],
            "query": parsed_request.query,
            "error": str(exc),
        }), 400
    except SearchExecutionTimeoutError as exc:
        return jsonify({
            "results": [],
            "query": parsed_request.query,
            "error": str(exc),
        }), 504
    except SearchExecutionBusyServiceError as exc:
        return jsonify({
            "results": [],
            "query": parsed_request.query,
            "error": str(exc),
        }), 503
    except Exception as e:
        logger.exception("搜索失败: %s", e)
        return jsonify({
            "results": [],
            "query": parsed_request.query,
            "error": str(e),
        }), 500


@app.route("/api/search/nl", methods=["POST"])
@rate_limit(lambda: get_settings().rate_limit_nl_per_min)
def api_search_nl():
    try:
        req_json = parse_json_object_body(request)
        message = req_json.get("message", "")
        # Get UI state to merge later
        ui_state = {
            "sidebar_source": req_json.get("sidebar_source"),
            "date_field": req_json.get("date_field"),
            "date_from": req_json.get("date_from"),
            "date_to": req_json.get("date_to"),
            "limit": req_json.get("limit")
        }
        
        result = nl_search_service.resolve_intent(message, ui_state)
        
        if result["kind"] == "out_of_scope":
            return jsonify({
                "kind": "capability_notice",
                "message": result["message"],
                "capabilities": result["capabilities"]
            })
            
        # It's search_intent
        resolved = result["resolved"]
        
        # Validate source enum
        source = resolved.get("source")
        if source not in ("all", "file", "mweb"):
            source = "all"
            
        # Clamp limit
        limit = resolved.get("limit")
        if limit is not None:
            try:
                limit = max(1, min(int(limit), 200))
            except (ValueError, TypeError):
                limit = None
                
        # Validate date_field
        date_field = resolved.get("date_field")
        if date_field not in ("mtime", "ctime"):
            date_field = "mtime"
                
        exact_focus = bool(resolved.get("exact_focus"))

        sanitized_resolved = {
            **resolved,
            "source": source,
            "limit": limit,
            "date_field": date_field,
            "exact_focus": exact_focus,
        }

        from .request_validation import SearchRequest
        search_req = SearchRequest(
            query=resolved["q"],
            source=source,
            date_field=date_field,
            date_from=resolved.get("date_from"),
            date_to=resolved.get("date_to"),
            limit=limit,
            exact_focus=exact_focus,
            path_filter=resolved.get("path_filter"),
            filename_only=bool(resolved.get("filename_only")),
        )
        
        search_res = search_service.search(search_req)
        
        return jsonify({
            "kind": "search_results",
            "query": search_res.query,
            "results": search_res.results,
            "resolved": sanitized_resolved
        })
    except RequestValidationError as exc:
        error_message, status = map_validation_error(exc)
        return jsonify({"error": error_message}), status
    except NLSearchServiceError as exc:
        return jsonify({"code": exc.code, "error": str(exc), "detail": exc.detail}), exc.status_code
    except SearchSourceNotAvailableError as exc:
        return jsonify({"error": str(exc)}), 400
    except SearchExecutionTimeoutError as exc:
        return jsonify({"error": str(exc)}), 504
    except SearchExecutionBusyServiceError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as e:
        logger.exception("NL 搜索失败: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/search/interpret/stream", methods=["POST"])
@rate_limit(lambda: get_settings().rate_limit_interpret_per_min)
def api_search_interpret_stream():
    try:
        req_json = parse_json_object_body(request)
        user_text = req_json.get("user_text", "")
        results = req_json.get("results", [])

        def generate():
            try:
                for chunk in search_interpret_service.interpret_stream(user_text, results):
                    yield chunk
            except Exception as e:
                logger.exception("生成解读发生异常: %s", e)
                import json
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        return Response(stream_with_context(generate()), mimetype="text/event-stream")
    except RequestValidationError as exc:
        error_message, status = map_validation_error(exc)
        return jsonify({"error": error_message}), status
    except SearchInterpretServiceError as exc:
        return jsonify({"code": exc.code, "error": str(exc), "detail": exc.detail}), exc.status_code
    except Exception as e:
        logger.exception("流式解读失败: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/search/interpret", methods=["POST"])
@rate_limit(lambda: get_settings().rate_limit_interpret_per_min)
def api_search_interpret():
    try:
        req_json = parse_json_object_body(request)
        user_text = req_json.get("user_text", "")
        results = req_json.get("results", [])
        
        interpretation = search_interpret_service.interpret(user_text, results)
        return jsonify({"interpretation": interpretation})
    except RequestValidationError as exc:
        error_message, status = map_validation_error(exc)
        return jsonify({"error": error_message}), status
    except SearchInterpretServiceError as exc:
        return jsonify({"code": exc.code, "error": str(exc), "detail": exc.detail}), exc.status_code
    except Exception as e:
        logger.exception("解读失败: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/api/reveal", methods=["POST"])
def api_reveal():
    """Reveal a file in macOS Finder."""
    try:
        parsed_request = parse_file_body_request(request)
        file_service.reveal_file(parsed_request)
    except RequestValidationError as exc:
        error_message, status = map_validation_error(exc)
        return jsonify({"ok": False, "error": error_message}), status
    except FileAuthorizationError as exc:
        body, status = _map_file_access_error(exc)
        return jsonify(body), status
    return jsonify({"ok": True})


@app.route("/api/open", methods=["POST"])
def api_open():
    """Open a file with default application (macOS)."""
    try:
        parsed_request = parse_file_body_request(request)
        file_service.open_file(parsed_request)
    except RequestValidationError as exc:
        error_message, status = map_validation_error(exc)
        return jsonify({"ok": False, "error": error_message}), status
    except FileAuthorizationError as exc:
        body, status = _map_file_access_error(exc)
        return jsonify(body), status
    return jsonify({"ok": True})


@app.route("/api/file/read", methods=["GET"])
def api_file_read():
    """
    Read a text preview of a file under indexed directories (for agents / skills).
    Query: filepath (required), max_bytes (optional, capped by config API_MAX_READ_BYTES).
    """
    try:
        parsed_request = parse_file_query_request(request, include_max_bytes=True)
        result = file_service.read_file_preview(parsed_request)
    except RequestValidationError as exc:
        error_message, status = map_validation_error(exc)
        return jsonify({"ok": False, "error": error_message}), status
    except BinaryPreviewNotAllowedError as exc:
        return jsonify({
            "ok": False,
            "error": "该文件为二进制或无法作为文本安全展示，请使用 /api/file/download",
            "filepath": exc.filepath,
        }), 400
    except FileAuthorizationError as exc:
        body, status = _map_file_access_error(exc)
        return jsonify(body), status
    except OSError as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({
        "ok": True,
        "filepath": result.filepath,
        "size": result.size,
        "truncated": result.truncated,
        "content": result.content,
    })


@app.route("/api/file/download", methods=["GET"])
def api_file_download():
    """Download a file under indexed directories (Content-Disposition: attachment)."""
    try:
        parsed_request = parse_file_query_request(request, include_max_bytes=False)
        result = file_service.prepare_file_download(parsed_request)
    except RequestValidationError as exc:
        error_message, status = map_validation_error(exc)
        return jsonify({"ok": False, "error": error_message}), status
    except FileAuthorizationError as exc:
        body, status = _map_file_access_error(exc)
        return jsonify(body), status
    return send_file(
        result.resolved_path,
        as_attachment=True,
        download_name=result.download_name,
        mimetype=result.mimetype,
    )


def main():
    """CLI entry: python -m everythingsearch.app"""
    setup_flask_dev_daily_file_logging()
    logger.info("启动 EverythingSearch 服务...")
    health_service.warmup_vectordb()

    debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")
    settings = get_settings()
    port = settings.port
    host = settings.host
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
