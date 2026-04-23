"""测试请求参数校验模块。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from everythingsearch.request_validation import (
    FileBodyRequest,
    FileQueryRequest,
    InvalidParameterError,
    MissingParameterError,
    SearchRequest,
    UnsupportedParameterError,
    parse_file_body_request,
    parse_file_query_request,
    parse_json_object_body,
    parse_search_request,
)


def _build_request(*, args: dict | None = None, json_body=None):
    """构造最小化请求对象。"""
    return SimpleNamespace(
        args=args or {},
        get_json=lambda silent=True: json_body,
    )


class TestParseSearchRequest:
    """测试搜索请求解析。"""

    def test_empty_query_is_valid(self):
        parsed = parse_search_request(_build_request(args={"q": ""}))
        assert parsed == SearchRequest(
            query="",
            source="all",
            date_field="mtime",
            date_from=None,
            date_to=None,
            limit=None,
            exact_focus=False,
        )

    def test_invalid_source_raises(self):
        with pytest.raises(UnsupportedParameterError):
            parse_search_request(_build_request(args={"source": "xyz"}))

    def test_invalid_date_field_raises(self):
        with pytest.raises(UnsupportedParameterError):
            parse_search_request(_build_request(args={"date_field": "abc"}))

    def test_invalid_date_from_raises(self):
        with pytest.raises(InvalidParameterError):
            parse_search_request(_build_request(args={"date_from": "abc"}))

    def test_invalid_date_to_raises(self):
        with pytest.raises(InvalidParameterError):
            parse_search_request(_build_request(args={"date_to": "abc"}))

    def test_invalid_limit_raises(self):
        with pytest.raises(InvalidParameterError):
            parse_search_request(_build_request(args={"limit": "abc"}))

    def test_limit_zero_is_clamped_to_one(self):
        parsed = parse_search_request(_build_request(args={"limit": "0"}))
        assert parsed.limit == 1

    def test_exact_focus_true_is_parsed(self):
        parsed = parse_search_request(_build_request(args={"exact_focus": "true"}))
        assert parsed.exact_focus is True

    def test_exact_focus_invalid_raises(self):
        with pytest.raises(InvalidParameterError):
            parse_search_request(_build_request(args={"exact_focus": "maybe"}))


class TestParseFileQueryRequest:
    """测试文件查询参数解析。"""

    def test_missing_filepath_raises(self):
        with pytest.raises(MissingParameterError):
            parse_file_query_request(_build_request(), include_max_bytes=True)

    def test_empty_filepath_raises(self):
        with pytest.raises(MissingParameterError):
            parse_file_query_request(
                _build_request(args={"filepath": "   "}),
                include_max_bytes=True,
            )

    def test_invalid_max_bytes_raises(self):
        with pytest.raises(InvalidParameterError):
            parse_file_query_request(
                _build_request(args={"filepath": "/tmp/a.txt", "max_bytes": "abc"}),
                include_max_bytes=True,
            )

    def test_zero_max_bytes_raises(self):
        with pytest.raises(InvalidParameterError):
            parse_file_query_request(
                _build_request(args={"filepath": "/tmp/a.txt", "max_bytes": "0"}),
                include_max_bytes=True,
            )

    def test_valid_file_query_request(self):
        parsed = parse_file_query_request(
            _build_request(args={"filepath": "/tmp/a.txt", "max_bytes": "128"}),
            include_max_bytes=True,
        )
        assert parsed == FileQueryRequest(filepath="/tmp/a.txt", max_bytes=128)


class TestParseFileBodyRequest:
    """测试文件 body 参数解析。"""

    def test_missing_body_raises(self):
        with pytest.raises(MissingParameterError):
            parse_file_body_request(_build_request(json_body=None))

    def test_missing_filepath_raises(self):
        with pytest.raises(MissingParameterError):
            parse_file_body_request(_build_request(json_body={}))

    def test_non_object_json_body_raises(self):
        with pytest.raises(InvalidParameterError):
            parse_file_body_request(_build_request(json_body=[]))

    def test_valid_body_request(self):
        parsed = parse_file_body_request(_build_request(json_body={"filepath": "/tmp/a.txt"}))
        assert parsed == FileBodyRequest(filepath="/tmp/a.txt")


class TestParseJsonObjectBody:
    """测试顶层 JSON 对象请求体解析。"""

    def test_missing_body_raises(self):
        with pytest.raises(MissingParameterError):
            parse_json_object_body(_build_request(json_body=None))

    def test_array_body_raises(self):
        with pytest.raises(InvalidParameterError):
            parse_json_object_body(_build_request(json_body=[]))

    def test_string_body_raises(self):
        with pytest.raises(InvalidParameterError):
            parse_json_object_body(_build_request(json_body="hello"))

    def test_valid_object_body(self):
        parsed = parse_json_object_body(_build_request(json_body={"message": "hi"}))
        assert parsed == {"message": "hi"}
