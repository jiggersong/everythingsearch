"""多模态端点消息内容的构造与解析。

Qwen3.6/3.7 系列为原生多模态模型，DashScope 原生 API 只在多模态端点提供服务，
其消息内容与返回内容均为分段列表（如 ``[{"text": "..."}]``），需与纯文本互转。
"""

from typing import Any, List


def to_parts(text: str) -> List[dict]:
    """把纯文本包装成多模态端点要求的分段列表。"""
    return [{"text": text}]


def to_text(content: Any) -> str:
    """把多模态端点返回的分段内容拼接回纯文本。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or "")
    if isinstance(content, list):
        return "".join(to_text(part) for part in content)
    return str(content)
