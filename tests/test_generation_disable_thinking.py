"""意图识别 / 结果解读调用 Generation 时须关闭思考模式，保证 JSON 与低延迟。"""

from unittest.mock import MagicMock, patch

from everythingsearch.services.nl_search_service import NLSearchService
from everythingsearch.services.search_interpret_service import SearchInterpretService


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


def test_nl_intent_disables_thinking():
    """意图识别须传 enable_thinking=False，避免思考模式破坏 JSON Mode。"""
    service = NLSearchService()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.output.choices[0].message.content = (
        '{"intent":"search","slots":{"q":"预算","source":null,"date_field":null,'
        '"date_from":null,"date_to":null,"limit":null,"match_mode":"balanced",'
        '"path_filter":null,"filename_only":null},"assistant_message":null,'
        '"capabilities":null}'
    )

    with patch(
        "everythingsearch.services.nl_search_service.get_settings",
        return_value=_mock_settings(),
    ), patch(
        "everythingsearch.services.nl_search_service.dashscope.Generation.call",
        return_value=mock_resp,
    ) as mock_call:
        service.resolve_intent("找预算相关文件", {})

    kwargs = mock_call.call_args.kwargs
    assert kwargs.get("enable_thinking") is False
    assert kwargs.get("model") == "qwen3.7-flash"
    assert kwargs.get("response_format") == {"type": "json_object"}


def test_interpret_disables_thinking():
    """结果解读亦关闭思考模式，降低延迟与费用。"""
    service = SearchInterpretService()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.output.choices[0].message.content = "共找到若干相关结果。"

    results = [
        {
            "filename": "a.md",
            "tag": "语义匹配",
            "relevance": "80%",
            "preview": "预算草案",
        }
    ]

    with patch(
        "everythingsearch.services.search_interpret_service.get_settings",
        return_value=_mock_settings(),
    ), patch(
        "everythingsearch.services.search_interpret_service.dashscope.Generation.call",
        return_value=mock_resp,
    ) as mock_call:
        service.interpret("预算", results)

    kwargs = mock_call.call_args.kwargs
    assert kwargs.get("enable_thinking") is False
    assert kwargs.get("model") == "qwen3.7-flash"
