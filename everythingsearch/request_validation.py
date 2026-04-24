"""请求参数校验辅助逻辑。"""

from __future__ import annotations

from dataclasses import dataclass


class RequestValidationError(Exception):
    """请求参数校验错误基类。"""


class MissingParameterError(RequestValidationError):
    """缺少必要参数。"""


class InvalidParameterError(RequestValidationError):
    """参数格式或类型非法。"""


class UnsupportedParameterError(RequestValidationError):
    """参数值不在支持范围内。"""


@dataclass(frozen=True)
class SearchRequest:
    """搜索接口请求参数。"""

    query: str
    source: str
    date_field: str
    date_from: float | None
    date_to: float | None
    limit: int | None
    #: True 时优先仅使用关键词倒排命中（意图为「精确检索」时由 NL 流程设置）；无命中时底层会回退为混合检索。
    exact_focus: bool = False
    #: 路径/目录名包含的关键字过滤。
    path_filter: str | None = None
    #: 是否仅在文件名中搜索
    filename_only: bool = False


@dataclass(frozen=True)
class FileQueryRequest:
    """文件查询接口请求参数。"""

    filepath: str
    max_bytes: int | None = None


@dataclass(frozen=True)
class FileBodyRequest:
    """文件 body 接口请求参数。"""

    filepath: str


def parse_json_object_body(flask_request) -> dict:
    """解析并校验顶层 JSON 对象请求体。"""
    payload = flask_request.get_json(silent=True)
    if payload is None:
        raise MissingParameterError("请求体必须是 JSON")
    if not isinstance(payload, dict):
        raise InvalidParameterError("请求体必须是 JSON 对象")
    return payload


def parse_search_request(flask_request) -> SearchRequest:
    """解析搜索请求参数。"""
    query = (flask_request.args.get("q", "") or "").strip()
    source = _parse_source(flask_request.args.get("source", "all"))
    date_field = _parse_date_field(flask_request.args.get("date_field", "mtime"))
    date_from = _parse_optional_float(flask_request.args.get("date_from"), "date_from")
    date_to = _parse_optional_float(flask_request.args.get("date_to"), "date_to")
    limit = _parse_optional_limit(flask_request.args.get("limit"))
    exact_focus = _parse_optional_bool(flask_request.args.get("exact_focus"), "exact_focus")
    path_filter = flask_request.args.get("path_filter")
    if path_filter:
        path_filter = path_filter.strip() or None
    filename_only = _parse_optional_bool(flask_request.args.get("filename_only"), "filename_only")
    return SearchRequest(
        query=query,
        source=source,
        date_field=date_field,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        exact_focus=exact_focus,
        path_filter=path_filter,
        filename_only=filename_only,
    )


def parse_file_query_request(flask_request, *, include_max_bytes: bool) -> FileQueryRequest:
    """解析文件查询接口请求参数。"""
    filepath = _parse_required_filepath(flask_request.args.get("filepath"))
    max_bytes = None
    if include_max_bytes:
        max_bytes = _parse_optional_positive_int(flask_request.args.get("max_bytes"), "max_bytes")
    return FileQueryRequest(filepath=filepath, max_bytes=max_bytes)


def parse_file_body_request(flask_request) -> FileBodyRequest:
    """解析文件 body 接口请求参数。"""
    payload = parse_json_object_body(flask_request)
    filepath = _parse_required_filepath(payload.get("filepath"))
    return FileBodyRequest(filepath=filepath)


def map_validation_error(exc: RequestValidationError) -> tuple[str, int]:
    """将输入校验异常映射为错误消息与状态码。"""
    return str(exc), 400


def _parse_source(raw_value: object) -> str:
    value = (str(raw_value or "all")).strip()
    if value not in {"all", "file", "mweb"}:
        raise UnsupportedParameterError("source 仅支持 all、file、mweb")
    return value


def _parse_date_field(raw_value: object) -> str:
    value = (str(raw_value or "mtime")).strip()
    if value not in {"mtime", "ctime"}:
        raise UnsupportedParameterError("date_field 仅支持 mtime、ctime")
    return value


def _parse_optional_float(raw_value: object, field_name: str) -> float | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError(f"{field_name} 必须是数字") from exc


def _parse_optional_limit(raw_value: object) -> int | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("limit 必须是整数") from exc
    return max(1, min(limit, 200))


def _parse_optional_positive_int(raw_value: object, field_name: str) -> int | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError(f"{field_name} 必须是整数") from exc
    if parsed < 1:
        raise InvalidParameterError(f"{field_name} 必须大于 0")
    return parsed


def _parse_optional_bool(raw_value: object, field_name: str) -> bool:
    if raw_value is None:
        return False
    value = str(raw_value).strip().lower()
    if not value:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise InvalidParameterError(f"{field_name} 必须是布尔值")


def _parse_required_filepath(raw_value: object) -> str:
    if raw_value is None:
        raise MissingParameterError("filepath 为必填参数")
    filepath = str(raw_value).strip()
    if not filepath:
        raise MissingParameterError("filepath 为必填参数")
    return filepath
