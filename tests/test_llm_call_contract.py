"""意图识别 / 结果解读的大模型调用契约测试。

Qwen3.6/3.7 系列为原生多模态模型，DashScope 原生 API 上仅由多模态端点提供服务，
走文本端点会返回 400 InvalidParameter（url error）。这里锁定调用端点、消息格式、
思考模式开关，以及上游错误详情不被吞掉。
"""

from unittest.mock import MagicMock, patch

import pytest

from everythingsearch.services.nl_search_service import (
    NLSearchService,
    NLSearchServiceError,
)
from everythingsearch.services.search_interpret_service import (
    SearchInterpretService,
    SearchInterpretServiceError,
)


def _mock_settings(**overrides):
    base = {
        "dashscope_api_key": "sk-test",
        "nl_intent_model": "qwen3.7-flash",
        "search_interpret_model": "qwen3.7-flash",
        "nl_timeout_sec": 10,
        "interpret_timeout_sec": 20,
        "nl_max_message_chars": 1000,
        "interpret_max_results": 10,
        "enable_mweb": False,
        "search_top_k": 30,
    }
    base.update(overrides)
    return MagicMock(**base)


def _intent_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.output.choices[0].message.content = [
        {
            "text": '{"intent":"search","slots":{"q":"预算","source":null,'
            '"date_field":null,"date_from":null,"date_to":null,"limit":null,'
            '"match_mode":"balanced","path_filter":null,"filename_only":null},'
            '"assistant_message":null,"capabilities":null}'
        }
    ]
    return resp


def _sample_results():
    return [
        {
            "filename": "a.md",
            "tag": "语义匹配",
            "relevance": "80%",
            "preview": "预算草案",
        }
    ]


def test_nl_intent_calls_multimodal_endpoint():
    """意图识别须走多模态端点，消息内容为分段列表，并关闭思考模式。"""
    service = NLSearchService()

    with patch(
        "everythingsearch.services.nl_search_service.get_settings",
        return_value=_mock_settings(),
    ), patch(
        "everythingsearch.services.nl_search_service.MultiModalConversation"
    ) as mock_client:
        mock_client.call.return_value = _intent_response()
        result = service.resolve_intent("找预算相关文件", {})

    kwargs = mock_client.call.call_args.kwargs
    assert kwargs["model"] == "qwen3.7-flash"
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["enable_thinking"] is False
    for message in kwargs["messages"]:
        assert isinstance(message["content"], list)
        assert "text" in message["content"][0]

    assert result["kind"] == "search_intent"
    assert result["resolved"]["q"] == "预算"


def test_nl_intent_upstream_failure_keeps_detail():
    """上游非 200 时，真实报错须透传，不能被自身异常处理吞掉。"""
    service = NLSearchService()
    failed = MagicMock()
    failed.status_code = 400
    failed.message = "url error, please check url！"

    with patch(
        "everythingsearch.services.nl_search_service.get_settings",
        return_value=_mock_settings(),
    ), patch(
        "everythingsearch.services.nl_search_service.MultiModalConversation"
    ) as mock_client:
        mock_client.call.return_value = failed
        with pytest.raises(NLSearchServiceError) as exc_info:
            service.resolve_intent("找预算相关文件", {})

    assert exc_info.value.code == "UPSTREAM_ERROR"
    assert "url error" in exc_info.value.detail


def test_interpret_calls_multimodal_endpoint_and_flattens_content():
    """解读走多模态端点，并把分段返回拼接为纯文本。"""
    service = SearchInterpretService()
    resp = MagicMock()
    resp.status_code = 200
    resp.output.choices[0].message.content = [{"text": "共 1 条"}, {"text": "相关结果。"}]

    with patch(
        "everythingsearch.services.search_interpret_service.get_settings",
        return_value=_mock_settings(),
    ), patch(
        "everythingsearch.services.search_interpret_service.MultiModalConversation"
    ) as mock_client:
        mock_client.call.return_value = resp
        text = service.interpret("预算", _sample_results())

    kwargs = mock_client.call.call_args.kwargs
    assert kwargs["model"] == "qwen3.7-flash"
    assert kwargs["enable_thinking"] is False
    assert text == "共 1 条相关结果。"


def test_interpret_upstream_failure_keeps_detail():
    """解读接口同样须透传上游错误详情。"""
    service = SearchInterpretService()
    failed = MagicMock()
    failed.status_code = 400
    failed.message = "url error, please check url！"

    with patch(
        "everythingsearch.services.search_interpret_service.get_settings",
        return_value=_mock_settings(),
    ), patch(
        "everythingsearch.services.search_interpret_service.MultiModalConversation"
    ) as mock_client:
        mock_client.call.return_value = failed
        with pytest.raises(SearchInterpretServiceError) as exc_info:
            service.interpret("预算", _sample_results())

    assert exc_info.value.code == "UPSTREAM_ERROR"
    assert "url error" in exc_info.value.detail


def test_interpret_stream_flattens_list_chunks():
    """流式解读须能解析分段列表增量，输出 SSE delta。"""
    service = SearchInterpretService()

    def _chunk(text):
        item = MagicMock()
        item.status_code = 200
        item.output.choices[0].message.content = [{"text": text}]
        return item

    with patch(
        "everythingsearch.services.search_interpret_service.get_settings",
        return_value=_mock_settings(),
    ), patch(
        "everythingsearch.services.search_interpret_service.MultiModalConversation"
    ) as mock_client:
        mock_client.call.return_value = [_chunk("共 1 条"), _chunk("相关结果。")]
        payload = "".join(service.interpret_stream("预算", _sample_results()))

    assert "共 1 条" in payload
    assert "相关结果。" in payload
    assert "event: done" in payload
