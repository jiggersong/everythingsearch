# Changelog

[English](CHANGELOG.en.md) | [中文](CHANGELOG.md)

本文件记录 EverythingSearch 面向使用者的可见变更。建议与 [GitHub Releases](https://github.com/jiggersong/everythingsearch/releases) 中的 Tag 一并维护（Release 说明可摘要自本文件对应版本）。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.3.2] - 2026-03-31

**GitHub Release**：[v1.3.2](https://github.com/jiggersong/everythingsearch/releases/tag/v1.3.2)

### 变更

- **Web 界面**：搜索页（`everythingsearch/templates/index.html`）视觉与交互优化，整体对齐 **Apple Human Interface Guidelines** 与 **Google Material Design 3** 的常见做法：系统字体栈与排版、胶囊搜索框与聚焦环、侧栏与历史项层次、结果卡片与筛选 Chip（pill）、分页与按钮触控尺寸、深浅色令牌与阴影；支持 `prefers-reduced-motion` 与 `focus-visible`，**不改变**既有搜索与 API 行为。
- **文档**：新增 `docs/UI_DESIGN_APPLE_GOOGLE.md`，记录上述 UI 方案与验收要点。

## [1.3.1] - 2026-03-27

**GitHub Release**：[v1.3.1](https://github.com/jiggersong/everythingsearch/releases/tag/v1.3.1)

### 修复

- **依赖（ChromaDB）**：将 `chromadb` 自 `1.5.2` 升级至 **`1.5.5`**。在 **Python 3.14** 与 **Pydantic 2.12+**（`BaseSettings` 已迁至 `pydantic-settings`）组合下，旧版 Chroma 会错误回退到 **`pydantic.v1`**，导入时在 `Settings` 上对 `chroma_server_nofile` 等字段触发 **`pydantic.v1.errors.ConfigError: unable to infer type for attribute "chroma_server_nofile"`**，导致 **`everythingsearch/incremental.py`** 及任何会 `import chromadb` 的入口无法启动。`1.5.5` 改为使用 **`pydantic_settings.BaseSettings`** 与 Pydantic v2 校验器，恢复正常导入与索引流程。

## [1.3.0] - 2026-03-26

**GitHub Release**：[v1.3.0](https://github.com/jiggersong/everythingsearch/releases/tag/v1.3.0)

### 变更

- **文档国际化统一升级**：`README`、`INSTALL`、`PROJECT_MANUAL`、`CHANGELOG` 全部补齐中英文版本，并在文档顶部提供中英文切换链接。
- **技术手册英文版对齐**：`docs/PROJECT_MANUAL.en.md` 按中文版结构重写，对齐章节编号、架构图、技术栈/配置表格、模块细节、运维与部署内容。
- **README 文档门户优化**：文档导读改为更规范的表格化门户（文档矩阵 + 技术手册范围），并合并重复信息。
- **入口精简**：移除冗余的 `README.en.md`，统一以 `README.md` 作为英文默认入口，`README.zh-CN.md` 作为中文入口。

## [1.2.3] - 2026-03-26

**GitHub Release**：[v1.2.3](https://github.com/jiggersong/everythingsearch/releases/tag/v1.2.3)

### 变更（合并 1.2.2 + 1.2.3）

- **增量索引启动兼容性**：修复 `everythingsearch/incremental.py` 在脚本方式启动（`python everythingsearch/incremental.py`）时可能触发的相对导入错误，统一使用绝对导入，避免 `ImportError: attempted relative import with no known parent package`。
- **新增快捷命令**：新增仓库根目录 `Makefile`，提供 `make index`、`make index-full`、`make app`、`make app-status`、`make app-restart`、`make app-stop`，简化日常索引与服务管理。
- **英文文档（默认）+ 中文可选**：新增 `README.zh-CN.md`、`docs/INSTALL.en.md`、`docs/PROJECT_MANUAL.en.md`、`docs/CHANGELOG.en.md`；`README.md` 作为英文默认入口，顶部提供中英文切换。

## [1.2.1] - 2026-03-23

**GitHub Release**：[v1.2.1](https://github.com/jiggersong/everythingsearch/releases/tag/v1.2.1)

### 变更

- **日志按天滚动**：新增仓库根目录 **`gunicorn.conf.py`**，Gunicorn 使用 `TimedRotatingFileHandler`（每日午夜切分）写入 `logs/app.log`、`logs/app_err.log`，归档文件带日期后缀（如 `app.log.2026-03-23`），默认保留 90 个备份；常驻启动改为 `-c gunicorn.conf.py`，不再使用 `--access-logfile` / `--error-logfile`。
- **Launchd / Shell**：`everythingsearch_start.sh` 将 wrapper 输出写入按日文件 **`logs/launchd_app_YYYY-MM-DD.log`**；`everythingsearch_index.sh` 将增量索引输出写入 **`logs/incremental_YYYY-MM-DD.log`**；示例与安装脚本生成的 plist 去掉固定 `/tmp/*.log` 的 `StandardOutPath`/`StandardErrorPath`，避免单文件无限增长。
- **开发模式**：`python -m everythingsearch.app` 通过 **`everythingsearch/logging_config.py`** 为应用与 Werkzeug 增加按天滚动的 `logs/app_dev.log`、`logs/werkzeug_dev.log`。
- **文档**：`docs/PROJECT_MANUAL.md`、`docs/INSTALL.md`、`scripts/run_app.sh` 等与上述路径及用法对齐。

### 说明

- 已安装过 LaunchAgent 的环境请重新执行 **`scripts/install_launchd_wrappers.sh`**（或重装时重新生成 wrapper），以更新 `~/.local/bin/` 下脚本。

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
