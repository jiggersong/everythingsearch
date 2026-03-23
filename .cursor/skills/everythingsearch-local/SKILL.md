---
name: everythingsearch-local
description: >-
  Queries the EverythingSearch local semantic file index over HTTP (search, read
  text, download files). Use when the user needs to find documents on disk by
  meaning or keywords, read indexed file contents, inspect search snippets, or
  fetch files via the local EverythingSearch service — or when they mention
  EverythingSearch, 本地语义搜索, 本机文件搜索, or port 8000 search API.
---

# EverythingSearch 本地 API（Skills）

本 Skill 指导 Agent 通过 **本机已启动的 EverythingSearch HTTP 服务**（默认 `http://127.0.0.1:8000`）完成：语义/关键词搜索、查看结果片段、读取文本正文、下载文件。

## 前置条件

1. 用户已在本机运行搜索服务（例如项目目录下 `./scripts/run_app.sh start` 或 `./venv/bin/python -m everythingsearch.app`）。
2. 若连接失败，提示用户先启动服务并确认端口（环境变量 `PORT` 或 `config.PORT`，默认 `8000`）。
3. 可选环境变量 `EVERYTHINGSEARCH_BASE`：若用户将服务绑在其他地址/端口，用该值作为基址（须带 scheme，如 `http://127.0.0.1:8000`）。

## 基址

```
BASE="${EVERYTHINGSEARCH_BASE:-http://127.0.0.1:8000}"
```

以下示例用 `$BASE` 表示。

## 1. 搜索（片段即 `preview`）

语义与关键词混合检索；结果中 **`preview` 字段** 为围绕命中的短片段（与 Web 一致）。

```bash
curl -sG "$BASE/api/search" \
  --data-urlencode "q=你的自然语言或关键词" \
  --data-urlencode "source=all" \
  --data-urlencode "limit=30"
```

- `source`: `all` | `file` | `mweb`（若实例关闭 MWeb，勿用 `mweb`）。
- `limit`: 可选，限制条数，最大 `200`。

响应 JSON：`results[]` 含 `filename`, `filepath`, `preview`, `relevance`, `tag`, `mtime`, `source_type` 等。

## 2. 读取文件正文（文本）

仅允许 **已索引根目录（及可选 MWeb 目录）下** 的路径；用于查看完整或部分文本（受服务端 `API_MAX_READ_BYTES` 上限）。

```bash
curl -sG "$BASE/api/file/read" \
  --data-urlencode "filepath=/absolute/path/to/file.md" \
  --data-urlencode "max_bytes=200000"
```

成功时：`ok`, `filepath`, `size`, `truncated`, `content`。

若返回 400 提示二进制，改用下载接口。

## 3. 下载文件

浏览器或 `curl -OJ` 保存附件（路径请用 `--data-urlencode` 编码）：

```bash
curl -fL -OJ -G "$BASE/api/file/download" --data-urlencode "filepath=/absolute/path/to/file.bin"
```

## 4. Finder / 默认应用打开（可选）

与 Web 相同，需 POST JSON：

```bash
curl -s -X POST "$BASE/api/reveal" -H "Content-Type: application/json" \
  -d '{"filepath":"/absolute/path/to/file"}'
```

## 5. 健康检查（可选）

用于确认服务存活与大致状态（向量库文档数、搜索内存缓存条目数等）：

```bash
curl -s "$BASE/api/health"
```

## 6. 清空搜索内存缓存（可选）

索引大规模更新后，若需尽快避免重复查询命中旧结果：

```bash
curl -s -X POST "$BASE/api/cache/clear"
```

## 安全说明

- `/api/file/read` 与 `/api/file/download` **仅允许** `config.TARGET_DIR`（及 `ENABLE_MWeb` 时 `MWEB_DIR`）下的真实文件路径；其他路径返回 404。
- `/api/health` 会返回运行状态与数据规模摘要；服务应仅监听本机或受信网络，不要将未鉴权实例暴露到公网。

## Agent 工作流建议

1. 先调用 `/api/search` 拿到 `filepath` 与 `preview`。
2. 若片段不足，再 `/api/file/read` 拉取正文（注意 `truncated`）。
3. 二进制或大文件用 `/api/file/download` 交给用户本地处理。
