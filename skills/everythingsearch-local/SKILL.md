---
name: everythingsearch-local
description: >-
  Queries the EverythingSearch local HTTP service (default port 8000): hybrid
  vector/keyword search, natural-language intent search (DashScope), intelligent
  result interpretation, read/download indexed files. Use when the user needs to
  find local documents by meaning or keywords, analyze search hits, read file
  contents, or fetch files — or when they mention EverythingSearch, 本地语义搜索,
  自然语言搜索, 智能解读, 本机文件搜索, or port 8000 search API.
---

# EverythingSearch 本地 API（Skills）

本 Skill 指导 Agent 通过 **本机已启动的 EverythingSearch HTTP 服务**（默认 `http://127.0.0.1:8000`）完成：

- **直接搜索**：`GET /api/search`（向量 + 关键词混合，不经过大模型）
- **自然语言搜索**：`POST /api/search/nl`（DashScope 意图识别 → 结构化检索，可触发「精确优先」路径）
- **搜索结果智能解读**：`POST /api/search/interpret` 或 `/api/search/interpret/stream`（基于当前结果列表的短总结）
- **读文本 / 下载 / 在 Finder 中揭示** 等与历史一致的能力

设计细节与 Web 行为见仓库内 `docs/NL_SEARCH_AND_WEB_UI.md`；完整路由与配置见 `docs/PROJECT_MANUAL.md` 第 4.6 节。

## 前置条件

1. 用户已在本机运行搜索服务（例如 `./scripts/run_app.sh start` 或 `./venv/bin/python -m everythingsearch.app`）。
2. 若连接失败，提示用户先启动服务并确认端口（环境变量 `PORT` 或 `config.PORT`，默认 `8000`）。
3. 可选环境变量 `EVERYTHINGSEARCH_BASE`：若服务绑在其他地址/端口，用该值作为基址（须带 scheme，如 `http://127.0.0.1:8000`）。

```
BASE="${EVERYTHINGSEARCH_BASE:-http://127.0.0.1:8000}"
```

### 智能能力对 DashScope API Key 的依赖

- **`GET /api/search`**：不调用生成式模型；仅需本地向量库已构建（嵌入阶段仍需要 Key 建索引）。
- **`POST /api/search/nl`**、**`/api/search/interpret*`**：服务端需配置 **`DASHSCOPE_API_KEY`**（或 `config` 中等价项）。未配置时这些接口会返回业务错误（如 `MISSING_API_KEY`），Agent 应退化为 **`GET /api/search`** 完成检索。
- 意图识别与解读会访问外网模型服务；默认限流见配置 `RATE_LIMIT_NL_PER_MIN`、`RATE_LIMIT_INTERPRET_PER_MIN`（常见默认各约每分钟每 IP 10 次，以 `everythingsearch/infra/settings.py` 为准）。

## 1. 直接搜索（混合检索，无大模型）

语义与关键词混合检索；结果中 **`preview`** 为围绕命中的短片段。

```bash
curl -sG "$BASE/api/search" \
  --data-urlencode "q=你的关键词或短句" \
  --data-urlencode "source=all" \
  --data-urlencode "limit=30"
```

可选查询参数（与校验逻辑一致时）：`date_field`（`mtime`|`ctime`）、`date_from`、`date_to`、`limit`（1～200）。

- `source`: `all` | `file` | `mweb`（若实例关闭 MWeb，勿用 `mweb`）。
- **注意**：`GET /api/search` **没有** `exact_focus` 参数；「精确优先」检索仅由下面的 NL 路径在解析出 `exact_focus` 后触发。

响应 JSON：`results[]` 含 `filename`, `filepath`, `preview`, `relevance`, `tag`（如「语义匹配」「精确匹配」）, `mtime`, `source_type` 等；另有 `query` 字段。

## 2. 自然语言搜索（意图 → 检索）

将用户整句自然语言交给模型解析为结构化检索参数（核心检索词 `slots.q`、来源、时间、`match_mode` 等），再执行与 Web 相同的搜索管线。

```bash
curl -s -X POST "$BASE/api/search/nl" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我找去年关于预算的 excel",
    "sidebar_source": "all",
    "date_field": "mtime",
    "date_from": null,
    "date_to": null,
    "limit": 30
  }'
```

- **请求体**：`message`（必填字符串）；可选 `sidebar_source`、`date_field`、`date_from`、`date_to`、`limit` —— 与 UI 侧一致，用于与模型输出合并、约束检索。
- **成功且为检索意图**：`kind: "search_results"`，`results` 与 `/api/search` 同形，`resolved` 含归一化后的 `q`、`source`、`date_field`、`exact_focus`、`match_mode` 等。
- **超出能力范围**：`kind: "capability_notice"`（或等价结构），含 `message`、`capabilities`，**无** `results`。
- **错误**：可能含 `code`（如 `MISSING_API_KEY`）、`error`、`detail`；超时/繁忙可能为 504/503。

当模型将 `match_mode` 设为 **`exact_focus`** 时，后端设 `exact_focus=true`：先关键词优先路径，无命中或全部被筛掉时再回退混合检索（见 `docs/NL_SEARCH_AND_WEB_UI.md`）。

## 3. 搜索结果智能解读

在已有 **`results` 数组**（通常来自上一步搜索响应）的基础上，生成简短自然语言总结，说明精确/语义匹配分层、相关度等。

**非流式：**

```bash
curl -s -X POST "$BASE/api/search/interpret" \
  -H "Content-Type: application/json" \
  -d '{
    "user_text": "用户原始查询或意图描述",
    "results": [ ... ]
  }'
```

成功：`{"interpretation": "..."}`。`results` 为空时服务端可能直接返回固定短句（如不调用模型）。

**流式（SSE）：**

```bash
curl -sN -X POST "$BASE/api/search/interpret/stream" \
  -H "Content-Type: application/json" \
  -d '{"user_text":"...","results":[...]}'
```

响应为 `text/event-stream`；需 DashScope Key。解读只会取每条结果的部分字段（含 `tag`、`preview` 截断等），条数上限见配置 `INTERPRET_MAX_RESULTS`。

## 4. 读取文件正文（文本）

仅允许 **已索引根目录（及可选 MWeb 目录）下** 的路径；受服务端 `API_MAX_READ_BYTES` 上限。

```bash
curl -sG "$BASE/api/file/read" \
  --data-urlencode "filepath=/absolute/path/to/file.md" \
  --data-urlencode "max_bytes=200000"
```

成功时：`ok`, `filepath`, `size`, `truncated`, `content`。

若返回 400 提示二进制，改用下载接口。

## 5. 下载文件

```bash
curl -fL -OJ -G "$BASE/api/file/download" --data-urlencode "filepath=/absolute/path/to/file.bin"
```

## 6. Finder / 默认应用打开（可选）

与 Web 相同，需 POST JSON：

```bash
curl -s -X POST "$BASE/api/reveal" -H "Content-Type: application/json" \
  -d '{"filepath":"/absolute/path/to/file"}'
```

`POST /api/open` 用默认应用打开文件，请求体同为 `{"filepath": "..."}`，见 `docs/PROJECT_MANUAL.md`。

## 7. 健康检查（可选）

```bash
curl -s "$BASE/api/health"
```

## 8. 清空搜索内存缓存（可选）

索引大规模更新后，若需尽快避免重复查询命中旧结果：

```bash
curl -s -X POST "$BASE/api/cache/clear"
```

## 安全说明

- `/api/file/read` 与 `/api/file/download` **仅允许** `config.TARGET_DIR`（及 `ENABLE_MWeb` 时 `MWEB_DIR`）下的真实文件路径；其他路径返回 404。
- `/api/health` 会返回运行状态与数据规模摘要；服务应仅监听本机或受信网络，不要将未鉴权实例暴露到公网。
- NL 与解读接口依赖外部模型，应注意 Key 与限流，避免对公网暴露。

## Agent 工作流建议

1. **默认**：`GET /api/search` 拿 `filepath` 与 `preview`（无 Key、或只需简单查询时）。
2. **需要整句意图、精确优先策略时**：在确认 Key 可用或用户接受错误回退的前提下用 `POST /api/search/nl`。
3. **需要「这些结果意味着什么」的短总结时**：在已有 `results` 上调用 `POST /api/search/interpret`（或流式）。
4. 若片段不足，再 `GET /api/file/read` 拉取正文（注意 `truncated`）；二进制或大文件用 `GET /api/file/download`。
