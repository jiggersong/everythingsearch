import argparse
import json
import logging
import sys
import os

from everythingsearch.infra.settings import get_settings
from everythingsearch.services.file_service import FileService
from everythingsearch.services.health_service import HealthService
from everythingsearch.services.search_service import SearchService
from everythingsearch.services.nl_search_service import NLSearchService

def setup_cli_logging():
    """配置 CLI 模式下的日志，只输出 ERROR 级别，防止干扰标准输出 JSON。"""
    # 禁用各类库的冗余日志
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    
    # 将 root logger 级别设置为 ERROR
    logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
    
    # 强制压制一些嘈杂的 logger
    import jieba
    jieba.setLogLevel(logging.ERROR)
    
    for logger_name in ["everythingsearch", "langchain", "chromadb", "sentence_transformers", "httpx", "urllib3", "jieba"]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.ERROR)
        # 确保不向上传递
        logger.propagate = False
        # 如果有 handler，保证 handler 的 level 也是 ERROR
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setLevel(logging.ERROR)
            logger.addHandler(handler)

def run_search(query: str, limit: int, source: str, json_output: bool):
    """执行搜索命令逻辑。"""
    try:
        settings = get_settings()
        
        search_service = SearchService()
        health_service = HealthService(search_service=search_service)
        nl_search_service = NLSearchService()
        
        # 确保向量数据库加载
        health_service.ensure_warmup()
        
        ui_state = {
            "sidebar_source": source,
            "limit": limit
        }
        
        # 解析意图
        result = nl_search_service.resolve_intent(query, ui_state)
        
        if result["kind"] == "out_of_scope":
            error_data = {
                "error": result.get("message", "当前请求不在支持范围内"),
                "capabilities": result.get("capabilities", [])
            }
            if json_output:
                print(json.dumps(error_data, ensure_ascii=False))
            else:
                print(f"Error: {error_data['error']}")
            sys.exit(1)
            
        resolved = result["resolved"]
        
        # 验证和修正参数
        resolved_source = resolved.get("source")
        if resolved_source not in ("all", "file", "mweb"):
            resolved_source = "all"
            
        resolved_limit = resolved.get("limit")
        if resolved_limit is not None:
            try:
                resolved_limit = max(1, min(int(resolved_limit), 200))
            except (ValueError, TypeError):
                resolved_limit = None
                
        date_field = resolved.get("date_field")
        if date_field not in ("mtime", "ctime"):
            date_field = "mtime"
            
        exact_focus = bool(resolved.get("exact_focus"))
        
        from everythingsearch.request_validation import SearchRequest
        search_req = SearchRequest(
            query=resolved.get("q", query),
            source=resolved_source,
            date_field=date_field,
            date_from=resolved.get("date_from"),
            date_to=resolved.get("date_to"),
            limit=resolved_limit or limit,
            exact_focus=exact_focus,
            path_filter=resolved.get("path_filter"),
            filename_only=bool(resolved.get("filename_only")),
        )
        
        search_res = search_service.search(search_req)
        
        # 构造结果字典
        results_list = []
        for doc in search_res.results:
            # 兼容 dataclass 或者 dict
            doc_dict = doc if isinstance(doc, dict) else (getattr(doc, '__dict__', doc))
            # 为了纯净输出，提取 Agent 最需要的核心字段
            item = {
                "filepath": doc_dict.get("filepath") or getattr(doc, "filepath", ""),
                "score": doc_dict.get("score") or getattr(doc, "score", 0.0),
                "snippet": doc_dict.get("snippet") or getattr(doc, "snippet", ""),
                "mtime": doc_dict.get("mtime") or getattr(doc, "mtime", 0.0)
            }
            results_list.append(item)
            
        output_data = {
            "query": search_res.query,
            "results": results_list
        }
        
        if json_output:
            print(json.dumps(output_data, ensure_ascii=False))
        else:
            print(f"Query: {output_data['query']}")
            for item in output_data['results']:
                print(f"- [{item['score']:.2f}] {item['filepath']}")
                print(f"  {item['snippet']}")
                
    except Exception as e:
        error_data = {"error": str(e)}
        if json_output:
            print(json.dumps(error_data, ensure_ascii=False))
        else:
            print(f"Error: {e}")
        sys.exit(1)

def main():
    setup_cli_logging()
    
    parser = argparse.ArgumentParser(description="EverythingSearch CLI")
    parser.add_argument("query", type=str, help="搜索词或自然语言查询")
    parser.add_argument("--limit", "-n", type=int, default=10, help="限制返回的结果数量")
    parser.add_argument("--source", type=str, default="all", choices=["all", "file", "mweb"], help="指定搜索来源")
    parser.add_argument("--json", action="store_true", help="强制以 JSON 格式输出")
    
    args = parser.parse_args()
    
    run_search(args.query, args.limit, args.source, args.json)

if __name__ == "__main__":
    main()
