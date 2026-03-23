# Changelog

本文件记录 EverythingSearch 面向使用者的可见变更。建议与 [GitHub Releases](https://github.com/jiggersong/everythingsearch/releases) 中的 Tag 一并维护（Release 说明可摘要自本文件对应版本）。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.1.0] - 2025-03-23

**GitHub Release**：[v1.1.0](https://github.com/jiggersong/everythingsearch/releases/tag/v1.1.0)

### 新增

- **HTTP**：`GET /api/health` — 返回运行时间、向量库状态与文档数、搜索内存缓存条目数等（仅适合本机或受信网络）。
- **HTTP**：`POST /api/cache/clear` — 清空搜索内存缓存（全量/增量索引重建后若不想等服务重启或等待 TTL，可主动调用）。
- **测试**：`tests/` 与 `pytest.ini`，覆盖搜索缓存键、Embedding 缓存与连接池、Flask API、索引辅助函数等。

### 变更

- **搜索**（`search.py`）：对相同查询条件做短期内存缓存（默认 TTL 20 分钟、最多 100 条）；在 **Unix/macOS** 上为单次搜索设置约 30 秒 `SIGALRM` 超时（无 `SIGALRM` 的环境则不做闹钟超时）；向量库缓存清理时同步清空搜索缓存。
- **Embedding 缓存**（`embedding_cache.py`）：SQLite **WAL**、固定大小连接池、旧版仅两列表结构自动 `ALTER` 增加 `created_at`；统计计数使用 `PrivateAttr` 锁，避免 Pydantic 初始化问题。
- **索引**（`indexer.py`）：全量重建时按文档平均长度选择向量化 **batch**（约 25 / 40 / 55）。
- **应用**（`app.py`）：启动或首个请求前尝试预热向量库连接。

### 说明

- 搜索超时基于进程级闹钟，**不宜**依赖其在多线程高并发下对「每一请求」独立计时；生产若使用多线程 Worker，请知悉该限制。
- `/api/health` 会暴露运行状态与大致数据规模，**请勿将未鉴权服务暴露到公网**。

## [1.0.0] - 此前

初始公开版本能力以 README 与 PROJECT_MANUAL 描述为准（语义搜索、增量索引、Web UI、本地 ChromaDB 等）。

后续版本可同样打 Tag、发 Release，并在本节为对应版本增加 Release 链接。
