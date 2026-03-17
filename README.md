# EverythingSearch

EverythingSearch 是一个运行在 macOS 上的**本地文件语义搜索引擎**。它允许用户通过自然语言或关键词，快速查找存储在本地的文档、代码和资料。

> 类似 Windows 上的 Everything，但增加了语义理解能力——不仅能精确匹配文件名，还能理解自然语言描述（如"去年的营销方案"）并找到相关文档。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![macOS](https://img.shields.io/badge/macOS-10.15%2B-lightgrey)
![License](https://img.shields.io/badge/License-Apache%202.0-green)

## 功能特性

- **语义搜索**：基于向量相似度的自然语言搜索，不局限于关键词精确匹配
- **混合索引**：同时索引文件内容和文件名，确保仅靠文件名也能搜到（如图片、视频等媒体文件）
- **MWeb 笔记集成（可选）**：可搜索 MWeb 导出的 Markdown 笔记，通过 `ENABLE_MWEB=False` 可完全关闭
- **位置加权**：关键词出现在文件名、标题中的结果获得更高排名
- **Embedding 缓存**：已生成过的向量不会重复调用 API，大幅加速后续索引重建
- **增量索引**：支持每日自动检测文件变更，仅对新增/修改/删除的文件更新索引
- **隐私优先**：索引和数据库完全本地化（ChromaDB），仅在生成向量时调用云端 API
- **Web 搜索界面**：浏览器中搜索，支持来源过滤、排序、分页、关键词高亮、Finder 定位

## 技术架构

```
┌───────────────────────────────────────────────┐
│              WebUI (浏览器)                      │
│   搜索 / 过滤 / 排序 / 分页 / 高亮 / Finder定位   │
└─────────────────────┬─────────────────────────┘
                      │ HTTP (localhost:8000)
┌─────────────────────▼─────────────────────────┐
│            Flask 后端 (app.py)                  │
│    /api/search · /api/reveal · /api/open       │
└─────────────────────┬─────────────────────────┘
                      │
┌─────────────────────▼─────────────────────────┐
│           搜索引擎 (search.py)                  │
│  向量搜索 · 位置加权 · 关键词回退 · 文件去重       │
└─────────────────────┬─────────────────────────┘
                      │
┌─────────────────────▼─────────────────────────┐
│         ChromaDB (本地向量数据库)                │
└─────────────────────┬─────────────────────────┘
                      │
┌─────────────────────▼─────────────────────────┐
│   索引构建 (indexer.py / incremental.py)        │
│  文件扫描 · 内容解析 · 标题提取 · 文本切分        │
└─────────────────────┬─────────────────────────┘
                      │
┌─────────────────────▼─────────────────────────┐
│   Embedding 服务 (embedding_cache.py)          │
│  CachedEmbeddings → SQLite 缓存 → DashScope   │
└───────────────────────────────────────────────┘
```

### 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| 开发语言 | Python 3.11 | 推荐 3.11（或 3.10） |
| 编排框架 | LangChain | 文档加载、切分和向量化流程编排 |
| 向量模型 | Aliyun DashScope text-embedding-v2 | 中文理解好，成本极低 |
| 向量数据库 | ChromaDB | 本地文件型数据库，无需 Docker |
| Web 框架 | Flask + Gunicorn | 开发/生产 HTTP 服务 |
| 文件解析 | pypdf / python-docx / openpyxl / python-pptx | PDF、Word、Excel、PPT 内容提取 |
| 前端 | 单文件 HTML + CSS + JS | 无需 Node.js 构建 |

## 快速开始

### 前置条件

- macOS 10.15+
- Python 3.10 或 3.11
- [阿里云 DashScope API Key](https://dashscope.console.aliyun.com/apiKey)（费用极低，约 ¥0.0007 / 1000 tokens）

### 自动安装（推荐）

```bash
git clone https://github.com/jiggersong/everythingsearch.git
cd everythingsearch
./install.sh
```

安装脚本会交互式引导你完成配置（API Key、索引目录、MWeb 等）。

### 手动安装

```bash
git clone https://github.com/jiggersong/everythingsearch.git
cd everythingsearch

# 创建虚拟环境并安装依赖
python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt

# 创建配置文件并编辑
cp config.example.py config.py
# 编辑 config.py：填写 API Key 和索引目录

# 构建首次索引
caffeinate -i ./venv/bin/python incremental.py --full

# 启动搜索服务
./venv/bin/python app.py
```

浏览器打开 http://127.0.0.1:8000 开始搜索。

## 配置说明

所有配置集中在 `config.py` 中（从 `config.example.py` 复制）。

### 必填配置

| 配置项 | 说明 |
|--------|------|
| `MY_API_KEY` | DashScope API Key（推荐使用环境变量 `DASHSCOPE_API_KEY`） |
| `TARGET_DIR` | 要索引的文件根目录，支持单目录或列表 |

### 可选配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `ENABLE_MWEB` | `False` | 是否启用 MWeb 数据源 |
| `SEARCH_TOP_K` | `250` | 向量检索候选数量 |
| `SCORE_THRESHOLD` | `0.35` | 相关度阈值（越小越严格） |
| `CHUNK_SIZE` | `500` | 文本切分块大小 |
| `MAX_CONTENT_LENGTH` | `20000` | 单文件最大索引字符数 |

### 搜索调优

- **结果太少**：调大 `SCORE_THRESHOLD`（如 0.55）或调大 `SEARCH_TOP_K`
- **结果太杂**：调小 `SCORE_THRESHOLD`（如 0.30）
- **搜索太慢**：调小 `SEARCH_TOP_K`（如 100）

## 日常使用

### 启动搜索服务

```bash
# 开发模式（前台运行）
./venv/bin/python app.py

# 常驻模式（后台运行，需配合 launchd）
./run_app.sh start
./run_app.sh status    # 查看状态
./run_app.sh restart   # 重启
./run_app.sh stop      # 停止
```

### 增量索引

```bash
# 增量更新（仅处理变更文件）
./venv/bin/python incremental.py

# 完整重建
caffeinate -i ./venv/bin/python incremental.py --full

# 索引完成后重启搜索服务以加载新数据
./run_app.sh restart
```

### 开机自启（可选）

项目提供 macOS launchd 配置文件，支持搜索服务开机自启和每日定时增量索引。运行 `install.sh` 时可选择安装，或参考 [INSTALL.md](INSTALL.md) 手动配置。

## 支持的文件类型

| 类型 | 后缀 | 索引方式 |
|------|------|----------|
| 文本文件 | `.txt` `.md` `.py` `.js` `.json` `.html` `.css` `.java` `.go` `.ts` 等 | 全文索引 |
| 办公文档 | `.pdf` `.docx` `.xlsx` `.pptx` | 内容解析后索引 |
| 媒体文件 | `.jpg` `.png` `.mp4` `.mp3` `.zip` `.psd` 等 | 仅索引文件名 |

## 文档

- [INSTALL.md](INSTALL.md) — 详细安装与配置指引
- [PROJECT_MANUAL.md](PROJECT_MANUAL.md) — 项目技术说明书（架构、模块详解、调参指南）

## 许可证

本项目采用 [Apache License 2.0](LICENSE) 开源。
