# 自然语言搜索与 Web UI 行为说明

本文档描述 **当前实现** 与 `docs/PROJECT_MANUAL.md` 中搜索章节一致的设计要点，便于评审与联调。`dev_docs/` 中的内容属于开发过程文档；对外可参考的当前行为以本文件与 `PROJECT_MANUAL` 为准。

## 1. 目标

- Web 端在已配置 DashScope API Key 时，**默认**使用「意图识别 → 结构化检索 → 可选智能解读」，无需页面开关。
- 未配置 Key 时，前端**不调用** `/api/search/nl` 与解读接口，仅使用 `GET /api/search`（向量 + 关键词混合，与历史行为一致）。
- 用户明确要求**字面/精确**查找时，由大模型输出 `slots.match_mode = "exact_focus"`，后端走关键词优先路径；**无命中或全部被来源/时间筛掉**时，**回退**混合检索。

## 2. 组件与数据流

| 环节 | 模块 | 说明 |
|------|------|------|
| 意图 | `everythingsearch/services/nl_search_service.py` | DashScope JSON：`slots.q`、可选 `match_mode`、`source`、时间等 |
| 检索 | `everythingsearch/services/search_service.py` → `search_core` | `SearchRequest.exact_focus` 传入 `search.py` |
| 混合/精确 | `everythingsearch/search.py` | `exact_focus=True` 时先 `_keyword_fallback`；空结果则 `exact_focus` 逻辑回退后继续向量分支 |
| 解读 | `everythingsearch/services/search_interpret_service.py` | 流式/非流式；依赖结果中的 `tag`（精确匹配 / 语义匹配） |
| 限流 | `everythingsearch/infra/rate_limiting.py` | `RATE_LIMIT_NL_PER_MIN`、`RATE_LIMIT_INTERPRET_PER_MIN` |
| 页面 | `everythingsearch/templates/index.html` | `smart_search_available` 控制是否走 NL |

## 3. API 契约摘要

- **`POST /api/search/nl`**  
  - 请求体：`message`、可选 `sidebar_source`、`date_field`、`date_from`、`date_to`、`limit`。  
  - 成功：`kind: search_results`，`results` 同 `/api/search`，`resolved` 含归一化后的 `source`、`match_mode`、`exact_focus` 等。

- **`GET /api/search`**  
  - 无 `exact_focus` 查询参数；仅 NL 路径会设置 `SearchRequest.exact_focus`。

## 4. 配置项（`infra/settings.py` / `config.py` / 环境变量）

已移除 `NL_SEARCH_ENABLED`。与 NL 相关的项包括：`NL_INTENT_MODEL`、`SEARCH_INTERPRET_MODEL`、超时、`NL_MAX_MESSAGE_CHARS`、`INTERPRET_MAX_RESULTS`、两类限流、`TRUST_PROXY`。详见 `PROJECT_MANUAL` 配置表。

## 5. 已知取舍

- 意图依赖模型输出质量；`match_mode` 非法值会归一为 `balanced`（见 `nl_search_service.resolve_intent`）。
- `search_interpret_service` 中非 DashScope 异常仍可能经宽捕获转为 500（历史实现，本次未改）。
