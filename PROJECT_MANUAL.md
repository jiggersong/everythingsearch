# EverythingSearch 项目说明书

## 1. 项目概述

EverythingSearch 是一个运行在 macOS 上的**本地文件语义搜索引擎**。它允许用户通过自然语言或关键词，快速查找存储在本地的文档、代码和资料。

### 核心能力

- **语义搜索**：不局限于关键词精确匹配，能理解自然语言描述（如"去年的营销方案"）并找到相关文档
- **混合索引**：同时索引文件内容和文件名，确保仅靠文件名也能搜到（如图片、视频）
- **MWeb 笔记集成（可选）**：可搜索 MWeb 导出的 Markdown 笔记，结果中以标签区分来源；不需要时可通过 `ENABLE_MWEB=False` 完全关闭
- **位置加权**：关键词出现在文件名、标题中的结果会获得更高的排名
- **Embedding 缓存**：已生成过的向量不会重复调用 API，大幅加速索引重建
- **增量索引**：支持每日自动检测文件变更，仅对新增/修改/删除的文件更新索引
- **隐私与成本平衡**：索引和数据库完全本地化（ChromaDB），仅在生成向量时调用云端 API（阿里通义千问 DashScope）
- **WebUI 搜索界面**：浏览器中搜索，支持来源过滤、排序、分页、关键词高亮、Finder 定位

---

## 2. 技术架构

```
┌──────────────────────────────────────────────────────┐
│                    WebUI (浏览器)                      │
│   index.html · 搜索/过滤/排序/分页/高亮/Finder定位      │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP (localhost:8000)
┌───────────────────────▼──────────────────────────────┐
│               Flask 后端 (app.py)                      │
│       /api/search · /api/reveal · /api/open           │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│             搜索引擎 (search.py)                       │
│  向量搜索 · 位置加权 · 关键词回退 · 文件去重 · 来源过滤   │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│            ChromaDB (本地向量数据库)                     │
│  collection: local_files · cosine 距离                 │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│     索引构建 (indexer.py / incremental.py)              │
│  文件扫描 · 内容解析 · 标题提取 · 文本切分 · 向量生成     │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│     Embedding 服务 (embedding_cache.py)                │
│  CachedEmbeddings → SQLite 缓存 → DashScope API       │
└──────────────────────────────────────────────────────┘
```

### 技术栈

| 组件         | 选型                              | 说明                                      |
|-------------|-----------------------------------|------------------------------------------|
| 开发语言     | Python 3.11                       | 推荐 3.11（或 3.10）；请使用虚拟环境安装依赖 |
| 编排框架     | LangChain                         | 文档加载、切分和向量化流程编排               |
| 向量模型     | Aliyun DashScope text-embedding-v2 | 中文理解好，成本低                          |
| 向量数据库   | ChromaDB                          | 本地文件型数据库，无需 Docker               |
| Web 框架    | Flask + Gunicorn                  | 开发/生产 HTTP 服务                         |
| 文件解析     | pypdf / python-docx / openpyxl / python-pptx | PDF、Word、Excel、PPT 内容提取  |
| 前端        | 单文件 HTML + CSS + JS             | 无需 Node.js 构建                          |

---

## 3. 文件结构

```
EverythingSearch/
├── config.py              # 配置文件（从 config.example.py 复制，含 API Key 等）
├── config.example.py      # 配置模板（可提交，不含敏感信息）
├── indexer.py             # 全量索引构建（扫描文件+MWeb、解析内容、生成向量）
├── incremental.py         # 增量索引（检测变更、部分更新ChromaDB）
├── search.py              # 搜索核心（向量搜索、加权、去重、关键词回退）
├── embedding_cache.py     # Embedding 向量缓存层（SQLite + DashScope）
├── app.py                 # Flask Web 服务
│
├── templates/
│   └── index.html         # 搜索页面（单文件，含 CSS + JS）
├── static/
│   └── icon.png           # 页面图标
│
├── chroma_db/             # ChromaDB 向量数据库（自动生成）
├── embedding_cache.db     # Embedding 向量缓存（SQLite，自动生成）
├── scan_cache.db          # 扫描解析缓存（SQLite，未变更文件跳过解析，自动生成）
├── index_state.db         # 增量索引状态追踪（SQLite，自动生成）
├── logs/                  # 定时任务日志目录
│
├── com.jigger.everythingsearch.plist      # macOS launchd 定时索引任务 plist
├── com.jigger.everythingsearch.app.plist  # macOS launchd 搜索服务常驻 plist
├── run_app.sh                             # 搜索服务管理（start/stop/restart）
├── requirements.txt       # Python 依赖清单
├── venv/                  # Python 虚拟环境
│
├── PROJECT_MANUAL.md      # 本说明书
└── INSTALL.md             # 安装与配置指引

~/.local/bin/
├── everythingsearch_start.sh  # 搜索服务 launchd wrapper（安装时生成）
└── everythingsearch_index.sh  # 增量索引 launchd wrapper（安装时生成）
```

---

## 4. 核心模块详解

### 4.1 config.py — 配置中心

所有可调参数集中在此文件：

| 配置项 | 默认值 | 说明 |
|-------|--------|------|
| `MY_API_KEY` | `sk-...` 或 `DASHSCOPE_API_KEY` 环境变量 | 阿里通义千问 DashScope API Key |
| `TARGET_DIR` | `/path/to/documents` 或 `["/path1", "/path2"]` | 要索引的根目录（支持单目录或列表） |
| `ENABLE_MWEB` | `False/True` | 是否启用 MWeb 数据源；关闭后不会运行 MWeb 导出/扫描，且搜索页不会展示 MWeb 来源 |
| `MWEB_DIR` | `/path/to/MWebMarkDown/File` | MWeb 笔记导出目录 |
| `MWEB_EXPORT_SCRIPT` | `.../mweb_export.py` | MWeb 导出脚本路径 |
| `INDEX_STATE_DB` | `./index_state.db` | 增量索引状态数据库 |
| `SCAN_CACHE_PATH` | `./scan_cache.db` | 扫描解析缓存（未变更文件跳过解析） |
| `EMBEDDING_MODEL` | `text-embedding-v2` | 向量模型名称 |
| `CHUNK_SIZE` | `500` | 文本切分块大小（字符） |
| `CHUNK_OVERLAP` | `80` | 切分块重叠长度 |
| `MAX_CONTENT_LENGTH` | `20000` | 单文件最大索引字符数 |
| `SEARCH_TOP_K` | `250` | 向量检索候选 chunk 数量（越大召回越高但越慢） |
| `SCORE_THRESHOLD` | `0.45` | cosine 距离阈值（越小越严格） |
| `POSITION_WEIGHTS` | `filename:0.6, heading:0.8, content:1.0` | 位置加权因子 |
| `KEYWORD_FREQ_BONUS` | `0.03` | 关键词频次加分系数 |

**关于 API Key 的推荐做法**：
- 推荐使用环境变量 `DASHSCOPE_API_KEY`，避免把真实 Key 写进 `config.py`（尤其是在打包/传给其他电脑时）
- 若 Key 未配置：索引与搜索会直接报错并提示如何设置（这是预期行为）

### 4.2 indexer.py — 索引构建

**文件扫描**：递归遍历 `TARGET_DIR`（支持多目录列表），按后缀分类：
- **文本文件**（.txt, .md, .py 等）：直接读取
- **办公文档**（.pdf, .docx, .xlsx, .pptx）：通过子进程解析（防 C 扩展死锁，30s 超时）
- **媒体文件**（.jpg, .mp4 等）：仅索引文件名

**标题提取**：从各类文件中提取标题/heading，作为独立 chunk 存储，搜索时获得加权。

**MWeb 笔记扫描**：解析 YAML front matter（title、categories、mweb_uuid），提取 Markdown 标题，与文件采用相同的 chunk 结构。

**每个文件生成 3 类 chunk**：
1. `chunk_type: "filename"` — 文件名 + 路径摘要
2. `chunk_type: "heading"` — 提取的标题集合
3. `chunk_type: "content"` — 正文分块（每块 ~500 字符）

### 4.3 search.py — 搜索引擎

搜索管道流程：
1. **向量搜索**：在同一 collection 内进行相似度检索；可通过 `source=all|file|mweb` 过滤来源（若 `ENABLE_MWEB=False` 则仅返回文件来源）
2. **位置加权**：按 `chunk_type` 乘以权重因子，文件名匹配获 40% 提权
3. **关键词频次加权**：查询词出现多次的 chunk 额外加分
4. **文件去重**：同一文件只保留最佳 chunk
5. **关键词精确回退**：用 ChromaDB `$contains` 查找包含原文的文档（支持多词 OR）
6. **合并排序**：精确匹配 + 语义匹配合并，按分数排序返回

### 4.4 embedding_cache.py — 向量缓存

`CachedEmbeddings` 继承自 `DashScopeEmbeddings`，在调用 API 前先查 SQLite 缓存：
- 缓存 Key：`SHA256(model_name + "::" + text)`
- 缓存 Value：向量的 JSON 序列化
- 首次全量索引后，后续重建几乎无需 API 调用

### 4.5 incremental.py — 增量索引

使用 SQLite 表 `file_index` 追踪每个文件的 `(filepath, mtime, source_type)`：
- **新增文件**：生成向量并写入 ChromaDB
- **修改文件**（mtime 变化）：删除旧 chunk，重新索引
- **删除文件**（磁盘上不存在）：从 ChromaDB 和状态表中移除
- **未变文件**：跳过

**MWeb 可选开关**：
- `ENABLE_MWEB = False` 时：不会运行导出脚本，也不会扫描 MWeb 目录，搜索页不再显示 MWeb 来源

运行方式：
```bash
python incremental.py          # 增量更新
python incremental.py --full   # 完整重建
```

> **注意**：索引完成后需重启搜索服务以加载新数据：`./run_app.sh restart`

### 4.6 app.py — Web 服务

Flask 应用，路由：
- `GET /` — 返回搜索页面
- `GET /api/search?q=xxx&source=all|file|mweb` — 搜索 API
- `POST /api/reveal` — 在 Finder 中显示文件（含路径安全校验）
- `POST /api/open` — 用默认应用打开文件（含路径安全校验）

> 出于安全考虑，已移除以下接口：`/api/config`、`/api/health`、`/api/stats`、`/api/reload`。
> 索引重建后需重启搜索服务以加载新数据：`./run_app.sh restart`

**运行方式**：
- 开发：`./venv/bin/python app.py` 或 `./run_app.sh dev`
- 常驻：`./run_app.sh start`（gunicorn 后台）
- 管理：`./run_app.sh stop|restart|status`

### 4.7 launchd 常驻服务

> **macOS TCC 限制**：macOS Ventura 及以上版本对 `~/Documents` 目录有隐私保护（TCC），
> LaunchAgent 进程**无法直接访问**该路径下的脚本、`WorkingDirectory` 和日志文件。
> 因此 plist 通过调用 `~/.local/bin/` 下的 wrapper 脚本来绕过限制——wrapper
> 脚本由 bash 执行，在进程内部 `cd` 到项目目录并启动 gunicorn / 增量索引。
> plist 的 `StandardOutPath`/`StandardErrorPath` 指向 `/tmp/`（应用日志由 gunicorn 自身写入 `logs/` 目录）。

**搜索服务**（`com.jigger.everythingsearch.app.plist`）：
- `RunAtLoad` + `KeepAlive`：登录后自动启动，崩溃自动重启
- 通过 `~/.local/bin/everythingsearch_start.sh` 启动 gunicorn，端口 8000

**定时索引**（`com.jigger.everythingsearch.plist`）：
- 每天 10:00 执行增量索引，睡眠唤醒后补执行
- 通过 `~/.local/bin/everythingsearch_index.sh` 启动 `incremental.py`

**管理命令**（推荐使用 `launchctl bootstrap/bootout` 而非旧版 `load/unload`）：
```bash
# 查看状态
launchctl list | grep everythingsearch

# 重新加载搜索服务
launchctl bootout gui/$(id -u)/com.jigger.everythingsearch.app
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist

# 重新加载定时索引
launchctl bootout gui/$(id -u)/com.jigger.everythingsearch
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

---

## 5. 依赖资源

### 外部服务
- **阿里云 DashScope API**：用于生成文本向量（text-embedding-v2），需要有效的 API Key
  - 获取方式：注册阿里云账号 → 开通 DashScope 服务 → 创建 API Key
  - 费用：极低（约 ¥0.0007 / 1000 tokens）

### 本地资源
- macOS 10.15+ 系统
- Python 3.10 或 3.11（推荐 3.11）
- 磁盘空间：约 500MB（含虚拟环境和数据库）
- 网络：仅在索引构建时需要（调用 DashScope API），搜索时完全离线

---

## 6. 日常使用

### 启动搜索服务
```bash
cd /path/to/EverythingSearch
# 方式一：开发模式（前台）
./venv/bin/python app.py
# 或 ./run_app.sh dev

# 方式二：常驻模式（后台，支持重启）
./run_app.sh start
./run_app.sh status   # 查看状态
./run_app.sh restart  # 重启
./run_app.sh stop     # 停止
```
然后在浏览器打开 http://127.0.0.1:8000

### 手动触发增量索引
```bash
cd /path/to/EverythingSearch
./venv/bin/python incremental.py
# 索引完成后重启搜索服务以加载新数据
./run_app.sh restart
```

### 完整重建索引（首次或大规模变更后）
```bash
cd /path/to/EverythingSearch
caffeinate -i nohup ./venv/bin/python incremental.py --full > logs/full_rebuild.log 2>&1 &
# 索引完成后重启搜索服务以加载新数据
# ./run_app.sh restart
```
`caffeinate -i` 防止电脑睡眠中断进程。

### 查看增量索引日志
```bash
cat logs/incremental.log
cat logs/incremental_err.log
```

---

## 7. 维护与调参指南

### 调整搜索严格度
编辑 `config.py` 中的 `SCORE_THRESHOLD`：
- 调小（如 0.35）→ 更严格，只保留高相关结果
- 调大（如 0.60）→ 更宽松，结果更多但可能含噪声

### 增加索引目录
修改 `config.py` 中的 `TARGET_DIR`，然后执行 `python incremental.py --full` 重建。

### 更换 Embedding 模型
修改 `config.py` 中的 `EMBEDDING_MODEL`（需为 DashScope 支持的模型名），然后全量重建。缓存会自动因模型名不同而失效。

### 修改定时任务时间
1. 编辑 `com.jigger.everythingsearch.plist` 中的 `Hour` 和 `Minute`
2. 重新加载：
```bash
launchctl bootout gui/$(id -u)/com.jigger.everythingsearch
cp com.jigger.everythingsearch.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

### 添加新文件类型支持
在 `config.py` 中将新后缀添加到对应的集合（`TEXT_EXTENSIONS`、`OFFICE_EXTENSIONS` 或 `MEDIA_EXTENSIONS`），如需特殊解析器，在 `indexer.py` 的 `_read_file_worker` 中添加分支。

---

## 8. 从零部署指南

以下步骤适用于在一台全新的 Mac 电脑上部署本项目。

### 前置条件
- macOS 10.15+
- 已安装 Homebrew（如未安装：`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`)
- 阿里云 DashScope API Key

### 安装步骤

```bash
# 1. 安装 Python 3.11
brew install python@3.11

# 2. 将项目文件复制到目标位置
# （假设项目打包为 EverythingSearch.tar.gz）
mkdir -p ~/Documents/code
cd ~/Documents/code
tar xzf /path/to/EverythingSearch.tar.gz

# 3. 创建虚拟环境并安装依赖
cd EverythingSearch
python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt

# 4. 编辑配置文件
# 必须修改以下内容：
#   - MY_API_KEY: 你的 DashScope API Key
#   - TARGET_DIR: 你要索引的文件目录
#   - MWEB_DIR: MWeb 导出目录（如不用可忽略）
nano config.py

# 5. 构建首次索引
caffeinate -i ./venv/bin/python incremental.py --full

# 6. 启动搜索服务
./run_app.sh start
# 或开发模式: ./venv/bin/python app.py
# 浏览器打开 http://127.0.0.1:8000

# 7.（可选）搜索服务开机自启
#    注意：macOS TCC 限制 LaunchAgent 不能直接访问 ~/Documents，
#    需通过 ~/.local/bin/ 下的 wrapper 脚本启动。
mkdir -p ~/.local/bin
cat > ~/.local/bin/everythingsearch_start.sh << 'EOF'
#!/usr/bin/env bash
APP_DIR="$HOME/Documents/code/EverythingSearch"
mkdir -p "$APP_DIR/logs"
cd "$APP_DIR" || exit 1
exec "$APP_DIR/venv/bin/python" -m gunicorn -w 1 -b 127.0.0.1:8000 \
  --timeout 120 --access-logfile "$APP_DIR/logs/app.log" \
  --error-logfile "$APP_DIR/logs/app_err.log" app:app
EOF
chmod +x ~/.local/bin/everythingsearch_start.sh
cp com.jigger.everythingsearch.app.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist

# 8.（可选）安装定时增量索引
cat > ~/.local/bin/everythingsearch_index.sh << 'EOF'
#!/usr/bin/env bash
APP_DIR="$HOME/Documents/code/EverythingSearch"
mkdir -p "$APP_DIR/logs"
cd "$APP_DIR" || exit 1
exec "$APP_DIR/venv/bin/python" "$APP_DIR/incremental.py" \
  >> "$APP_DIR/logs/incremental.log" 2>&1
EOF
chmod +x ~/.local/bin/everythingsearch_index.sh
cp com.jigger.everythingsearch.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

---

## 9. 版权

© 2026 jiggersong. Licensed under the MIT License.
