# Changelog

本文件记录 EverythingSearch 面向使用者的可见变更。建议与 [GitHub Releases](https://github.com/jiggersong/everythingsearch/releases) 中的 Tag 一并维护（Release 说明可摘要自本文件对应版本）。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.2.0] - 2026-03-23

**GitHub Release**：[v1.2.0](https://github.com/jiggersong/everythingsearch/releases/tag/v1.2.0)

### 变更（仓库布局与运行入口）

- **目录结构**：文档迁至 `docs/`；安装与运维脚本迁至 `scripts/`（含 `install.sh`、`run_app.sh`、`run_tests.sh`、`launchd/` 示例）；Python 代码收拢为 **`everythingsearch/`** 包；配置模板在 **`etc/config.example.py`**（复制为仓库根目录 `config.py`）；默认数据与缓存路径在 **`data/`**（Chroma、Embedding 缓存、索引状态、扫描缓存等）；日志仍在 `logs/`。
- **启动方式**：Web 与 CLI 使用 `python -m everythingsearch.app`、`python -m everythingsearch.incremental`；生产环境 gunicorn 使用 **`everythingsearch.app:app`**。
- **launchd**：新增 **`scripts/install_launchd_wrappers.sh`**，用于在本机生成/更新 `~/.local/bin` 下 wrapper 与 `~/Library/LaunchAgents` plist，避免旧版 `app:app` 模块路径失效。
- **前端**：搜索页 favicon / Logo 使用 `url_for('static', …)`，避免硬编码静态路径。

### 变更（行为）

- **Embedding**：`CachedEmbeddings` 必须显式传入 **`cache_path`**（使用 `config.EMBEDDING_CACHE_PATH`），不再默认在项目根创建 `./embedding_cache.db`。

### 说明

- 从 v1.1.x 升级后请按 `README.md` / `docs/INSTALL.md` 核对路径，并视需要执行 `scripts/install_launchd_wrappers.sh` 或重新运行安装脚本以更新常驻服务。

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
- **应用**（`everythingsearch.app`）：启动或首个请求前尝试预热向量库连接。

### 说明

- 搜索超时基于进程级闹钟，**不宜**依赖其在多线程高并发下对「每一请求」独立计时；生产若使用多线程 Worker，请知悉该限制。
- `/api/health` 会暴露运行状态与大致数据规模，**请勿将未鉴权服务暴露到公网**。

## [1.0.0] - 此前

初始公开版本能力以 README 与 PROJECT_MANUAL 描述为准（语义搜索、增量索引、Web UI、本地 ChromaDB 等）。

后续版本可同样打 Tag、发 Release，并在本节为对应版本增加 Release 链接。
