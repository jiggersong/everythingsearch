import json
import logging
from typing import Any, Dict, List, Generator
import dashscope
try:
    from dashscope.common.error import DashScopeError
except ImportError:
    DashScopeError = Exception  # type: ignore[misc,assignment]

from ..infra.settings import get_settings

logger = logging.getLogger(__name__)

class SearchInterpretServiceError(Exception):
    def __init__(self, message: str, code: str, status_code: int = 500, detail: str = ""):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.detail = detail

class SearchInterpretService:

    def check_settings(self):
        settings = get_settings()
        if not settings.dashscope_api_key:
            raise SearchInterpretServiceError("未配置 API Key", "MISSING_API_KEY", 500)

    def _build_messages(self, user_text: str, results: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        settings = get_settings()
        
        results_subset = results[:settings.interpret_max_results]
        
        compact_results = []
        for i, r in enumerate(results_subset):
            rel = r.get("relevance", "0")
            compact_results.append({
                "index": i,
                "filename": r.get("filename", ""),
                "tag": r.get("tag", ""),
                "relevance": str(rel),
                "preview": str(r.get("preview", ""))[:200]
            })
            
        system_prompt = """你是一个专业的内网搜索结果解读助手。
你的任务是根据用户的检索词或意图，以及系统返回的摘要列表，给用户提供一段简短、直观的总体结果总结。

每条结果的字段含义（用于你判断「精确」还是「语义」）：
- tag 为「精确匹配」且 relevance 常为「关键词命中」：表示内容或索引块中**字面出现**了检索词，更贴近用户「找固定字样/专名/文件名片段」的诉求。
- tag 为「语义匹配」且 relevance 为百分比：表示向量相似度检索，更贴近「主题相近、表述不同」的诉求。

要求：
- 请使用与用户查询相同的语言进行响应。
- 基于 <search_results> 中的内容保持客观，不编造摘要中未提供的事实。
- 若用户查询看起来是在找**固定字面**（人名、代号、带引号片段、错误码等），而列表顶部是「精确匹配」，应明确点出「首条为关键词/字面命中，可能最符合精确查找」；若首条仅为语义匹配，则说明「更偏主题相似，可留意是否需更精确的关键词」。
- 若用户是宽泛主题检索，侧重说明相关度分层与排序靠前的结果为何可能更相关。
- 若匹配度整体较高，可提及排序靠前的一条更可能符合需求（与界面「猜你想找」呼应）。
- 用自然语言回答，段落简练，不要求输出 JSON，不要输出多余的套话。
- 界面已展示完整列表，你的说明聚焦匹配类型（精确/语义）、相关度与可选的浏览建议即可。
"""
        user_prompt = f"<user_query>\n{user_text}\n</user_query>\n<search_results>\n{json.dumps(compact_results, ensure_ascii=False)}\n</search_results>"
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

    def interpret(self, user_text: str, results: List[Dict[str, Any]]) -> str:
        if not results:
            return "未找到相关结果。"
            
        self.check_settings()
        settings = get_settings()
        dashscope.api_key = settings.dashscope_api_key
        messages = self._build_messages(user_text, results)
        
        try:
            response = dashscope.Generation.call(
                model=settings.search_interpret_model,
                messages=messages,
                result_format='message',
                timeout=settings.interpret_timeout_sec
            )
            if response.status_code != 200:
                if response.status_code == 429:
                    raise SearchInterpretServiceError("上游限流", "UPSTREAM_RATE_LIMIT", 503)
                raise SearchInterpretServiceError("上游模型调用失败", "UPSTREAM_ERROR", 502, detail=response.message)
            return response.output.choices[0].message.content or ""
        except DashScopeError as e:
            raise SearchInterpretServiceError("模型解读异常", "UPSTREAM_ERROR", 502, detail=str(e))
        except (TimeoutError, ConnectionError) as e:
            raise SearchInterpretServiceError("解读超时或网络异常", "UPSTREAM_TIMEOUT", 504, detail=str(e))
        except Exception as e:
            logger.exception("解读服务遇到未知异常")
            raise SearchInterpretServiceError("服务内部异常", "INTERNAL_ERROR", 500, detail=str(e))

    def interpret_stream(self, user_text: str, results: List[Dict[str, Any]]) -> Generator[str, None, None]:
        if not results:
            yield "data: " + json.dumps({"delta": "未找到相关结果。"}, ensure_ascii=False) + "\n\n"
            yield "event: done\ndata: {}\n\n"
            return
            
        self.check_settings()
        settings = get_settings()
        dashscope.api_key = settings.dashscope_api_key
        messages = self._build_messages(user_text, results)
        
        try:
            responses = dashscope.Generation.call(
                model=settings.search_interpret_model,
                messages=messages,
                result_format='message',
                stream=True,
                incremental_output=True,
                timeout=settings.interpret_timeout_sec
            )
            for resp in responses:
                if resp.status_code != 200:
                    yield f"event: error\ndata: {json.dumps({'error': resp.message})}\n\n"
                    break
                
                delta = resp.output.choices[0].message.content if resp.output.choices else ""
                if delta:
                    yield "data: " + json.dumps({"delta": delta}, ensure_ascii=False) + "\n\n"
            
            yield "event: done\ndata: {}\n\n"
            
        except DashScopeError as e:
            logger.exception("Stream error (DashScope API)")
            yield f"event: error\ndata: {json.dumps({'error': '模型流式解读异常', 'detail': str(e)})}\n\n"
        except (TimeoutError, ConnectionError) as e:
            logger.exception("Stream error (Network)")
            yield f"event: error\ndata: {json.dumps({'error': '模型流式响应超时或网络异常'})}\n\n"
