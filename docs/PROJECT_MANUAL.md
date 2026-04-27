# EverythingSearch 项目说明书

[English](PROJECT_MANUAL.en.md) | [中文](PROJECT_MANUAL.md)

## 1. 项目概述

EverythingSearch 是一个运行在 macOS 上的**本地文件语义搜索引擎**。它允许用户通过自然语言或关键词，快速查找存储在本地的文档、代码和资料。

### 核心能力

- **多路召回与混合检索 (Hybrid Retrieval)**：集成 SQLite FTS5 稀疏检索与 ChromaDB 稠密向量检索，利用 RRF（倒数排名融合）算法对文件名、标题、正文切块的召回结果进行无监督融合。
- **意图识别与 Query 规划 (Query Planning)**：支持自然语言大模型意图识别，动态解析时间范围、路径过滤与精确匹配等约束条件，生成结构化查询计划。
- **两阶段重排架构 (Two-stage Reranking)**：利用远端 Rerank 模型对初步融合结果进行深度语义重排，并结合基于文件粒度的聚合算分（File Aggregator）大幅提升排序准确率。
- **增量构建与多级缓存 (Incremental & Caching)**：提供基于修改时间的增量文件扫描，配合 Embedding 的 SQLite 持久化缓存以及查询级内存缓存，极大降低 API 调用开销并提升响应速度。
- **多源数据整合 (Data Ingestion)**：内建文档解析管道，支持跨进程异步提取 PDF/Word/Excel 等办公格式文本，提供无缝同步 MWeb 等 Markdown 笔记库的自动化支持。
- **本地优先设计 (Privacy & Local First)**：索引文件与分块向量等核心数据存留在本地，模型 API 仅负责执行基础 Embedding 和（可选的）前端请求的生成式解读。
- **标准化 API 面向 Agent 集成 (Agent-Friendly)**：系统功能高度服务化解耦，对外暴露稳定的 RESTful 接口（配有严密的文件越权防护），天然支持各类大模型 Agent 环境快速接入使用。

---

## 2. 技术架构

```
┌──────────────────────────────────────────────────────┐
│                    WebUI (浏览器)                      │
│   index.html · 搜索/过滤/排序/分页/高亮/Finder定位      │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP (localhost:8000)
┌───────────────────────▼──────────────────────────────┐
│            Flask 路由系统 (everythingsearch.app)       │
│  请求剥密、统一参数校验拦截 (request_validation) 返回400  │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│                核心业务编排层 (services/)               │
│ SearchService · FileService · HealthService ·         │
│ NLSearchService · SearchInterpretService              │
│ (含 file_access 统一文件越权防御及寻址保护)              │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│   多路检索管道 (everythingsearch.retrieval.pipeline)   │
│                                                        │
│  query_planner  ──→  意图解析、Query 结构化规划        │
│       │                                                │
│       ├──→  sparse_retriever (SQLite FTS5 稀疏召回)    │
│       └──→  dense_retriever  (ChromaDB 稠密召回)       │
│                    │                                   │
│                    ▼                                   │
│            fusion (RRF 倒数排名融合)                    │
│                    │                                   │
│                    ▼                                   │
│         reranking (DashScope Rerank 远端精排)          │
│                    │                                   │
│                    ▼                                   │
│        aggregation (文件级加权聚合, 按文件归并排序)      │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│   双存储引擎                                          │
│   ChromaDB (稠密向量)  +  SQLite FTS5 (稀疏全文索引)   │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│     索引构建 (indexer / incremental 模块)               │
│  文件扫描 · 内容解析 · 标题提取 · 文本切分 · 向量生成     │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│     Embedding 服务 (embedding_cache 模块)                │
│  CachedEmbeddings → SQLite 缓存 → DashScope API       │
└──────────────────────────────────────────────────────┘
```

### 技术栈


| 组件     | 选型                                           | 说明                          |
| ------ | -------------------------------------------- | --------------------------- |
| 开发语言   | Python 3.11                                  | 推荐 3.11（或 3.10）；请使用虚拟环境安装依赖 |
| 编排框架   | LangChain                                    | 文档加载、切分和向量化流程编排             |
| 向量模型   | Aliyun DashScope text-embedding-v2           | 中文理解好，成本低                   |
| 向量数据库  | ChromaDB                                     | 本地文件型数据库，无需 Docker          |
| 稀疏索引   | SQLite FTS5                                  | 全文检索，支持 BM25 加权排序           |
| Web 框架 | Flask + Gunicorn                             | 开发/生产 HTTP 服务               |
| 文件解析   | pypdf / python-docx / openpyxl / python-pptx | PDF、Word、Excel、PPT 内容提取     |
| 前端     | 单文件 HTML + CSS + JS                          | 无需 Node.js 构建               |


---

## 3. 文件结构

```text
EverythingSearch/
├── config.py                 # 本地配置（从 etc/config.example.py 复制，勿提交密钥）
├── etc/
│   └── config.example.py     # 配置模板
├── everythingsearch/         # Python 应用包
│   ├── __main__.py           # CLI 命令分发与应用入口
│   ├── cli.py                # 纯净输出终端命令行接口 (Agent 外脑支持)
│   ├── app.py                # Flask Web 路由入口及总线组装
│   ├── services/             # 业务服务层（抽象解耦核心逻辑）
│   │   ├── file_service.py   # 文件生命周期控制
│   │   ├── search_service.py # 搜索缓存控制及并发调度
│   │   ├── health_service.py # 数据探活与预热调度
│   │   ├── nl_search_service.py
│   │   └── search_interpret_service.py
│   ├── retrieval/            # ★ 核心多路检索与重排管道
│   │   ├── pipeline.py       # 搜索主链路编排
│   │   ├── query_planner.py  # 查询意图及参数规划
│   │   ├── sparse_retriever.py # FTS5 稀疏检索
│   │   ├── dense_retriever.py  # 向量稠密检索
│   │   ├── fusion.py         # RRF 融合算法
│   │   ├── reranking.py      # DashScope Rerank 接入
│   │   └── aggregation.py    # 文件级算分聚合
│   ├── indexing/             # 索引构建底层组件
│   │   ├── sparse_index_writer.py
│   │   ├── dense_index_writer.py
│   │   └── pipeline_indexer.py
│   ├── evaluation/           # 检索 benchmark、评测数据加载与指标计算
│   │   ├── benchmark_runner.py
│   │   ├── dataset.py
│   │   ├── metrics.py
│   │   └── datasets/
│   ├── infra/                # 基础设施层（含强类型配置 settings.py）
│   ├── request_validation.py # 入参验证协议 (提供统一400失败规范)
│   ├── file_access.py        # 强一致文件存取控制边界与防路径穿越
│   ├── indexer.py            # 全量索引构建入口
│   ├── incremental.py        # 增量索引入口
│   ├── embedding_cache.py    # Embedding 缓存层
│   ├── logging_config.py     # 标准化日志配置
│   ├── templates/            # Web UI 模板
│   │   └── index.html
│   └── static/               # 前端静态资源
│       ├── css/
│       ├── js/
│       └── icon.png
├── skills/                   # Agent Skill（支持 Cursor/Claude 等接入本地 API）
├── data/                     # 本地数据与缓存（默认路径，勿提交）
│   ├── chroma_db/            # ChromaDB 向量库
│   ├── sparse_index.db       # FTS5 稀疏索引数据库
│   ├── embedding_cache.db
│   ├── scan_cache.db
│   └── index_state.db
├── logs/                     # 运行与定时任务日志
├── scripts/                  # 运维与辅助脚本
│   ├── install.sh
│   ├── upgrade.sh             # 自动版本升级脚本 (v1.0+ → 最新版)
│   ├── install_launchd_wrappers.sh
│   ├── run_app.sh
│   ├── run_tests.sh
│   ├── audit_dependencies.py # 依赖审计
│   └── mweb_export.py        # MWeb 自动导出脚手架
├── docs/                     # 项目文档集
│   ├── CHANGELOG.md          # 更新日志
│   ├── INSTALL.md            # 部署安装指南
│   ├── PROJECT_MANUAL.md     # 技术架构文档（本文件）
│   ├── NL_SEARCH_AND_WEB_UI.md # 智能检索机制说明
│   ├── SEARCH_ACCURACY_TECHNICAL_DESIGN.md # 检索准确率设计方案
│   └── UI_DESIGN_APPLE_GOOGLE.md # UI 设计哲学
├── Makefile                  # make 快捷命令
├── requirements/             # 环境依赖清单
├── pytest.ini                # 单测配置
└── tests/                    # 单元测试与评测用例集

~/.local/bin/
├── everythingsearch_start.sh  # 搜索服务 launchd wrapper（安装时生成）
└── everythingsearch_index.sh  # 增量索引 launchd wrapper（安装时生成）
```

### 3.1 Agent Skill

面向 **Cursor、Claude Code 等支持 Agent Skills 的工具**，本仓库在根目录提供可版本化的 Skill 文件：


| 项目            | 说明                                                                                                                      |
| ------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **路径**        | `skills/everythingsearch-local/SKILL.md`                                                                                |
| **内容**        | 如何通过本机 HTTP API 完成混合搜索、自然语言意图搜索、结果智能解读、读文本/下载文件等；与 `docs/NL_SEARCH_AND_WEB_UI.md` 及下文 §4.6 路由一致                         |
| **基址**        | 默认 `http://127.0.0.1:8000`；若服务监听其他地址或端口，可在运行 Agent 的环境中设置 `EVERYTHINGSEARCH_BASE`（须含 scheme，例如 `http://127.0.0.1:8000`） |
| **DashScope** | NL 与解读接口需服务端配置有效 API Key；无 Key 时 Skill 中建议退化为 `GET /api/search`，见 Skill 正文「前置条件」                                        |


若你使用 Cursor 并希望加载本 Skill，请将 `skills/everythingsearch-local/` **复制**到当前工作区的 `.cursor/skills/everythingsearch-local/`，或在后者位置创建指向仓库内目录的**符号链接**，再按各工具文档刷新 Skills。

### 3.2 CLI 终端接口

为了支持缺乏独立 HTTP 请求能力的 LLM Agent (如 OpenClaw 等本机智能体环境)，项目提供了一个支持输出纯净 JSON 格式的命令行工具：

```bash
python -m everythingsearch search "<查询词>" --json
```

- 该接口与 Web 前端的自然语言搜索共享同一套意图识别与混合检索管道。
- 内部强制抑制了第三方库的冗余终端输出 (如 jieba 词典加载)，以确保 Agent 能够成功解析 `stdout` 中的 JSON 内容。
- 完整的接入指南与系统提示词示例，请查阅 `docs/OPENCLAW_INTEGRATION.md`。

---

## 4. 核心模块详解

### 4.1 config.py — 配置中心

本地兼容配置主要集中在此文件；运行时加载顺序为：环境变量 > 仓库根目录 `config.py` > 代码内安全默认值。


| 配置项                            | 默认值                                           | 说明                                        |
| ------------------------------ | --------------------------------------------- | ----------------------------------------- |
| `MY_API_KEY`                   | 空字符串或 `DASHSCOPE_API_KEY` 环境变量                | 阿里通义千问 DashScope API Key 的兼容字段；推荐优先使用环境变量 |
| `TARGET_DIR`                   | `/path/to/documents` 或 `["/path1", "/path2"]` | 要索引的根目录（支持单目录或列表；环境变量 `TARGET_DIR` 优先）    |
| `ENABLE_MWEB`                  | `False/True`                                  | 是否一键无缝开启内置 MWeb 笔记整合；开启后系统即接管内部自动导出       |
| `MWEB_LIBRARY_PATH`            | 默认系统库路径                                       | 指定 MWeb 主数据库目录（备用选项）                      |
| `MWEB_DIR`                     | `data/mweb_export`                            | 闭环自动管理的 MWeb 笔记存落地区                       |
| `INDEX_STATE_DB`               | `./index_state.db`                            | 增量索引状态数据库                                 |
| `SCAN_CACHE_PATH`              | `./scan_cache.db`                             | 扫描解析缓存（未变更文件跳过解析）                         |
| `EMBEDDING_MODEL`              | `text-embedding-v2`                           | 向量模型名称                                    |
| `CHUNK_SIZE`                   | `500`                                         | 文本切分块大小（字符）                               |
| `CHUNK_OVERLAP`                | `80`                                          | 切分块重叠长度                                   |
| `MAX_CONTENT_LENGTH`           | `20000`                                       | 单文件最大索引字符数                                |
| `SEARCH_TOP_K`                 | `250`                                         | 向量检索候选 chunk 数量（旧版 indexer 兼容保留字段；新管道使用 `DENSE_TOP_K`） |
| `SCORE_THRESHOLD`              | `0.35`                                        | cosine 距离阈值（越小越严格；与 `settings.py` 默认一致）   |
| `POSITION_WEIGHTS`             | `filename:0.60, heading:0.80, content:1.00`   | 位置加权因子                                    |
| `KEYWORD_FREQ_BONUS`           | `0.03`                                        | 关键词频次加分系数                                 |
| `SPARSE_TOP_K`                 | `120`                                         | SQLite FTS5 稀疏检索候选数量                         |
| `SPARSE_FILENAME_WEIGHT`       | `8.0`                                         | 稀疏检索文件名 BM25 权重                            |
| `SPARSE_PATH_WEIGHT`           | `3.0`                                         | 稀疏检索路径 BM25 权重                             |
| `SPARSE_HEADING_WEIGHT`        | `4.0`                                         | 稀疏检索标题 BM25 权重                             |
| `SPARSE_CONTENT_WEIGHT`        | `1.0`                                         | 稀疏检索正文 BM25 权重                             |
| `DENSE_TOP_K`                  | `120`                                         | 向量稠密检索候选数量                                |
| `FUSION_TOP_K`                 | `200`                                         | RRF 融合排序后的候选数量                             |
| `RRF_K`                        | `60`                                          | RRF 融合算法平滑常数                               |
| `RERANK_MODEL`                 | `gte-rerank`                                  | 远端精排模型名称（如 `qwen3-rerank`、`gte-rerank`）     |
| `RERANK_TOP_N`                 | `50`                                          | 送入 Rerank 精排的候选数量                           |
| `RERANK_MAX_DOC_CHARS`         | `2000`                                        | Rerank 阶段单文档截断字符数                           |
| `AGG_BEST_WEIGHT`              | `0.70`                                        | 文件聚合：最佳 chunk 权重                            |
| `AGG_SECOND_WEIGHT`            | `0.15`                                        | 文件聚合：次佳 chunk 权重                            |
| `AGG_THIRD_WEIGHT`             | `0.05`                                        | 文件聚合：第三 chunk 权重                            |
| `AGG_FILENAME_BONUS`           | `0.10`                                        | 文件聚合：命中文件名额外加分                            |
| `AGG_HEADING_BONUS`            | `0.05`                                        | 文件聚合：命中标题额外加分                             |
| `AGG_EXACT_BONUS`              | `0.10`                                        | 文件聚合：精确匹配额外加分                             |
| `AGG_MULTI_HIT_BONUS`          | `0.05`                                        | 文件聚合：多 chunk 命中额外加分                        |
| `AGG_LARGE_FILE_PENALTY`       | `0.05`                                        | 文件聚合：超大文件扣分系数                             |
| `INDEXER_BATCH_SIZE`           | `5000`                                        | 索引重建批次大小                                   |
| `EMBED_MAX_CHARS`              | `600`                                         | 单条 Embedding 文本截断字符数                        |
| `TRUST_PROXY`                  | `False`                                       | 是否信任反向代理传入的 `X-Forwarded-For`（限流取真实 IP）   |
| `NL_INTENT_MODEL`              | `qwen-turbo`                                  | 自然语言意图识别模型（建议选用支持 JSON Mode 的模型）          |
| `SEARCH_INTERPRET_MODEL`       | `qwen-turbo`                                  | 搜索结果「智能解读」所用模型                            |
| `NL_TIMEOUT_SEC`               | `10`                                          | 意图识别上游超时（秒）                               |
| `INTERPRET_TIMEOUT_SEC`        | `20`                                          | 解读上游超时（秒）                                 |
| `NL_MAX_MESSAGE_CHARS`         | `1000`                                        | 单次意图输入最大字符数                               |
| `INTERPRET_MAX_RESULTS`        | `10`                                          | 参与解读的摘要条数上限                               |
| `RATE_LIMIT_NL_PER_MIN`        | `10`                                          | `POST /api/search/nl` 每 IP 每分钟请求上限        |
| `RATE_LIMIT_INTERPRET_PER_MIN` | `10`                                          | 解读类接口每 IP 每分钟请求上限                         |


**关于 API Key 的推荐做法**：

- 推荐使用环境变量 `DASHSCOPE_API_KEY`，避免把真实 Key 写进 `config.py`（尤其是在打包/传给其他电脑时）
- 配置模板不再提供可运行的伪默认值；留空表示“未配置”，不是异常
- 若 Key 未配置：**增量/全量索引无法生成向量**（嵌入依赖 DashScope）。**Web 首页搜索**会退化为仅请求 `GET /api/search`，不调用意图识别与智能解读；若此时向量库亦不可用，搜索仍可能报错，需先完成索引并保证 Key 有效。
- 已移除历史上的 `NL_SEARCH_ENABLED` 开关：只要配置了 Key，Web 侧默认走智能检索流程（意图 + 混合检索 + 可选解读）。详见 `docs/NL_SEARCH_AND_WEB_UI.md`。

### 4.2 indexer.py — 索引构建

**文件扫描**：递归遍历 `TARGET_DIR`（支持多目录列表），按后缀分类：

- **文本文件**（.txt, .md, .py 等）：直接读取
- **办公文档**（.pdf, .docx, .xlsx, .pptx）：通过子进程解析（防 C 扩展死锁，30s 超时）
- **媒体文件**（.jpg, .mp4 等）：仅索引文件名

**标题提取**：从各类文件中提取标题/heading，作为独立 chunk 存储，搜索时获得加权。

**全量向量化 batch**：`calculate_batch_size(docs)` 按当前文档列表的平均 `page_content` 长度选择 batch（长文档约 25、中等约 40、较短约 55），以平衡 API 吞吐与单批体积。

**MWeb 笔记扫描**：解析 YAML front matter（title、categories、mweb_uuid），提取 Markdown 标题，与文件采用相同的 chunk 结构。

**每个文件生成 3 类 chunk**：

1. `chunk_type: "filename"` — 文件名 + 路径摘要
2. `chunk_type: "heading"` — 提取的标题集合
3. `chunk_type: "content"` — 正文分块（每块 ~500 字符）

### 4.3 `retrieval.pipeline` — 多路召回与重排引擎

搜索引擎的主链路采用多阶段检索架构：

```text
SearchRequest
  -> QueryPlanner
  -> SparseRetriever (SQLite FTS5)
  -> DenseRetriever (Embedding / Chroma 适配层)
  -> CandidateFusion (RRF)
  -> Reranker (DashScope qwen3-rerank Provider)
  -> FileAggregator
  -> ResultPresenter
```

**超时与繁忙保护**：
检索执行在业务层通过并发数控制与超时包装器（`SEARCH_TIMEOUT_SECONDS`，默认 30s）进行保护，超时或繁忙会向上抛出并转化为 504/503 响应。

**核心环节拆解**：

1. **Query Planner**：根据前端请求（包含可选的 `path_filter`, `date_field` 等）生成结构化的 `QueryPlan`。如果请求指定了 `exact_focus`，将直接退化为专注关键词的混合模式。
2. **Sparse Retriever (稀疏检索)**：利用新建的 `data/sparse_index.db` (SQLite FTS5) 进行快速的倒排索引查询，字段权重分配由 `SPARSE_FILENAME_WEIGHT`、`SPARSE_PATH_WEIGHT` 等配置项决定。
3. **Dense Retriever (稠密检索)**：利用现有的 ChromaDB 与 Embedding 层计算语义相似度，提取候选块。
4. **Candidate Fusion (RRF)**：通过 Reciprocal Rank Fusion 对稀疏和稠密的返回结果进行无监督融合。
5. **Reranker (二阶段精排)**：若配置了 `RERANK_MODEL`（如 DashScope 的 qwen3-rerank），将 RRF 产生的 Top N 候选发送给重排模型做深度语义打分。当重排模型超时或降级时，默认回退使用 RRF 分数。
6. **File Aggregator**：替代以往「单文件取最高分 chunk」的粗暴做法，基于所有候选 chunk 按文件粒度重新累加打分，提供更准确的排序。

### 4.4 embedding_cache.py — 向量缓存

`CachedEmbeddings` 继承自 `DashScopeEmbeddings`，在调用 API 前先查 SQLite 缓存：

- 缓存 Key：`SHA256(model_name + "::" + text)`
- 缓存 Value：向量的 JSON 序列化；写入时带 `created_at`（Unix 时间戳）
- 连接使用 **WAL**、**连接池**（固定数量连接复用）；若磁盘上已有旧表仅有 `(text_hash, vector)` 两列，初始化时会 **ALTER TABLE** 增加 `created_at`
- 命中/调用计数使用 `PrivateAttr` + `threading.Lock`，避免 Pydantic 对模型默认值做 deepcopy 时失败
- 首次全量索引后，后续重建几乎无需 API 调用

### 4.5 `everythingsearch.incremental` — 增量索引

使用 SQLite 表 `file_index` 追踪每个文件的 `(filepath, mtime, source_type)`：

- **新增文件**：生成向量并写入 ChromaDB
- **修改文件**（mtime 变化）：删除旧 chunk，重新索引
- **删除文件**（磁盘上不存在）：从 ChromaDB 和状态表中移除
- **未变文件**：跳过

**MWeb 可选开关**：

- `ENABLE_MWEB = False` 时：不会运行导出脚本，也不会扫描 MWeb 目录，搜索页不再显示 MWeb 来源

运行方式：

```bash
python -m everythingsearch.incremental          # 增量更新
python -m everythingsearch.incremental --full   # 完整重建
# 或（在仓库根目录）:
./venv/bin/python everythingsearch/incremental.py
```

> **注意**：索引完成后需重启搜索服务以加载新数据：`./scripts/run_app.sh restart`

### 4.6 `everythingsearch.app` 与服务编排层

`app.py` 专注于路由绑定层的职责：它将核心业务逻辑委派到 `services/` 子层统一处理；同时借由 `request_validation.py` 将所有异常、不合法 JSON 请求类型过滤出标准的 HTTP `400 Bad Request`，从而防止脏数据向下渗透带来 500 系统级崩溃。底层的 `file_access.py` 补充了一道屏障：无论外部调用如何发起文件读取、下载或者打开操作，均强制鉴权对应路径不能跨越索引边界（禁止路径穿越探测）。

**对外集成（Agent）**：面向 Cursor 等工具的 HTTP 调用示例、`EVERYTHINGSEARCH_BASE` 与无 Key 时的回退说明，见 §3.1 中的 `skills/everythingsearch-local/SKILL.md`。

Flask 应用路由（核心）：

- `GET /` — 返回搜索页面（模板注入 `smart_search_available`：是否已配置 DashScope API Key，用于前端选择 `POST /api/search/nl` 或退化为 `GET /api/search`）
- `GET /api/search?q=xxx&source=all|file|mweb` — 直接搜索 API（可选 `date_field` / `date_from` / `date_to` / `limit=1..200`；**不经过**大模型意图识别）
- `POST /api/search/nl` — 自然语言搜索：调用 DashScope 输出结构化意图（含 `slots.q`、可选 `match_mode`、时间来源等）→ 执行 `SearchService.search`（可带 `exact_focus`）；需 API Key 与网络可达模型服务
- `POST /api/search/interpret`、`POST /api/search/interpret/stream` — 基于当前结果列表生成简短「智能解读」（流式与非流式）；需 API Key，带每 IP 限流
- `GET /api/health` — 监控状态。其中当 `vectordb.status` 不等于 `"ok"` (如有损或降级)时，顶层 `ok` 标识会严格返回 `false`，保持内外状态的监控健康强一致性。
- `POST /api/cache/clear` — 清空搜索**内存缓存**
- `GET /api/file/read?filepath=...` — 读取**已索引根目录内**文件的文本内容
- `GET /api/file/download?filepath=...` — 下载**已索引根目录内**文件
- `POST /api/reveal` — 在 Finder 中显示文件
- `POST /api/open` — 用默认应用打开文件

> 出于安全考虑，以下接口仍不提供：`/api/config`、`/api/stats`、`/api/reload`。
> 索引重建后需重启搜索服务以加载新数据：`./scripts/run_app.sh restart`

**运行方式**：

- 开发：`./venv/bin/python -m everythingsearch.app` 或 `./scripts/run_app.sh dev`
- 常驻：`./scripts/run_app.sh start`（gunicorn 后台）
- 管理：`./scripts/run_app.sh stop|restart|status`

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

- 每 **30 分钟**执行一次增量索引，睡眠唤醒后补执行
- 通过 `~/.local/bin/everythingsearch_index.sh` 启动 `python -m everythingsearch.incremental`

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

- **阿里云 DashScope API**：需要有效的 API Key
  - **嵌入**：生成文本向量（默认 `text-embedding-v2`），索引构建阶段调用
  - **生成式**（可选）：当 Web 使用 `POST /api/search/nl` 或解读接口时，调用配置的 `NL_INTENT_MODEL` / `SEARCH_INTERPRET_MODEL`（默认 `qwen-turbo`），此时**搜索会话需要外网**
  - 获取方式：注册阿里云账号 → 开通 DashScope 服务 → 创建 API Key
  - 费用：极低（嵌入约 ¥0.0007 / 1000 tokens；意图/解读按所选模型计费）

### 本地资源

- macOS 10.15+ 系统
- Python 3.10 或 3.11（推荐 3.11）
- 磁盘空间：约 500MB（含虚拟环境和数据库）
- 网络：索引构建需要（嵌入 API）；若仅使用 `GET /api/search` 且向量已构建，查询阶段可不访问 DashScope；使用 NL 搜索或解读时需要外网

---

## 6. 日常使用

### Makefile 快捷命令

```bash
cd /path/to/EverythingSearch
make help          # 列出全部 make 目标及一行说明
make index         # 增量索引
make index-full    # 全量重建索引
make app           # 前台启动应用
make app-status    # 查看常驻服务状态
make app-restart   # 重启常驻服务
make app-stop      # 停止常驻服务
```

`make help` 与仓库根目录 `Makefile` 中的 `help` 目标同步维护；忘记子命令时可优先执行 `make help`。

### 启动搜索服务

```bash
cd /path/to/EverythingSearch
# 方式一：开发模式（前台）
./venv/bin/python -m everythingsearch.app
# 或 ./scripts/run_app.sh dev

# 方式二：常驻模式（后台，支持重启）
./scripts/run_app.sh start
./scripts/run_app.sh status   # 查看状态
./scripts/run_app.sh restart  # 重启
./scripts/run_app.sh stop     # 停止
```

然后在浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)

### 手动触发增量索引

```bash
cd /path/to/EverythingSearch
./venv/bin/python -m everythingsearch.incremental
# 索引完成后重启搜索服务以加载新数据
./scripts/run_app.sh restart
```

### 完整重建索引（首次或大规模变更后）

```bash
cd /path/to/EverythingSearch
caffeinate -i nohup ./venv/bin/python -m everythingsearch.incremental --full >> "logs/full_rebuild_$(date +%Y-%m-%d).log" 2>&1 &
# 索引完成后重启搜索服务以加载新数据
# ./scripts/run_app.sh restart
```

`caffeinate -i` 防止电脑睡眠中断进程。

### 版本升级（从旧版本迁移）

如果已安装过 v1.0.0 之后任一旧版本，可通过自动升级脚本将数据和配置迁移到当前最新版。

**操作流程：**

1. **下载新版到新目录**（不要把新版直接覆盖旧目录）：

   ```bash
   git clone https://github.com/jiggersong/everythingsearch.git ~/Downloads/EverythingSearch-new
   cd ~/Downloads/EverythingSearch-new
   ```

2. **运行升级脚本**（默认检测 `~/Documents/code/EverythingSearch`）：

   ```bash
   ./scripts/upgrade.sh [旧项目路径]
   ```

3. **按脚本提示确认**每一步操作：版本检测 → 代码同步 → 数据备份 → 配置合并 → 数据清理 → 依赖更新 → launchd 更新 → 索引重建。

4. **清理**：升级完成后，新下载的目录（如 `~/Downloads/EverythingSearch-new`）可直接删除；旧项目目录已更新为最新版，继续使用即可。

升级场景说明：

| 场景 | 旧版本 | 操作概要 |
|------|--------|----------|
| A | v1.0.x–v1.1.x | 删除旧索引，全量重建 |
| B | v1.2.0–v1.5.2 | 删除不兼容 ChromaDB，保留 embedding 缓存，全量重建 |
| C | v2.0.0+ | 格式兼容，仅合并配置新字段，建议运行增量索引验证 |

详见 [INSTALL.md](INSTALL.md) 第九节。

### 查看增量索引日志

```bash
# 按日文件：incremental_YYYY-MM-DD.log（stdout/stderr 合并写入）
ls -1 logs/incremental_*.log
tail -n 200 logs/incremental_$(date +%Y-%m-%d).log
```

### 6.5 系统权限与自动化设置

本节说明如何在 macOS 上配置开机自动启动、定时索引调度，以及解决 Python 后台进程的磁盘访问权限弹框问题。

#### 开机自动启动（搜索服务）

搜索服务通过 launchd 的 `RunAtLoad + KeepAlive` 机制实现开机自启。安装脚本（`install.sh`）会自动完成以下操作：

1. 生成 `~/.local/bin/everythingsearch_start.sh` wrapper 脚本
2. 将 `com.jigger.everythingsearch.app.plist` 复制到 `~/Library/LaunchAgents/`
3. 通过 `launchctl bootstrap` 注册服务

注册后，每次登录 macOS 时搜索服务将自动启动，崩溃后也会自动重启。无需手动干预。

**手动注册或重新注册**：

```bash
# 如需手动注册（迁移新机器时）
mkdir -p ~/.local/bin
cp scripts/launchd/com.jigger.everythingsearch.app.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist

# 验证是否已注册
launchctl list | grep everythingsearch
```

> **为什么通过 wrapper 脚本而非直接写路径？**  
> macOS TCC（隐私保护）限制 LaunchAgent 不能直接将 `~/Documents/` 下的路径写在 plist 的 `WorkingDirectory` 或 `StandardOutPath` 等字段中。Wrapper 脚本放在 `~/.local/bin/`（不受限制），由 bash 执行后在内部 `cd` 到项目目录，从而绕过限制。

#### 定时索引（每日自动增量更新）

增量索引由 `com.jigger.everythingsearch.plist` 控制，默认每 **30 分钟**执行一次，电脑睡眠期间错过的任务会在唤醒后自动补执行。

**手动注册或重新注册**：

```bash
mkdir -p ~/.local/bin
cp scripts/launchd/com.jigger.everythingsearch.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

**修改执行时间**（例如改为 8:30）：

```bash
# 1. 编辑 plist，修改 Hour 和 Minute 的值
nano ~/Library/LaunchAgents/com.jigger.everythingsearch.plist

# 2. 重新加载使配置生效
launchctl bootout gui/$(id -u)/com.jigger.everythingsearch
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist

# 验证
launchctl list | grep everythingsearch
```

#### 完全磁盘访问授权（解决权限弹框）

**问题现象**：每次定时索引执行时，macOS 弹出"python3.11 想访问其他 App 的数据"弹框，需要手动点击"允许"。

**原因**：launchd 以后台进程方式运行 Python，macOS 的 TCC（透明度、同意和控制）机制会拦截对受保护目录（如 MWeb 的 `~/Library/...` 数据库）的访问，直到用户在系统设置中显式授权。

**解决方法：授予 Python 完全磁盘访问权限**

首先确认实际使用的 Python 可执行文件路径：

```bash
readlink -f ./venv/bin/python
# 示例输出：/opt/homebrew/Cellar/python@3.11/3.11.15/Frameworks/Python.framework/Versions/3.11/bin/python3.11
```

然后在系统设置中完成授权：

1. 打开 **系统设置** → **隐私与安全性** → **完全磁盘访问**
2. 点击左下角「**＋**」按钮
3. 按 `Cmd+Shift+G` 输入上方命令输出的完整路径，点击「打开」
4. 同样方式再添加 `/bin/bash`（launchd 先通过 bash 调用 wrapper 脚本）
5. 确保两个条目的开关均处于「**开启**」状态

授权完成后，定时索引将静默在后台运行，不再弹出权限确认框。

> **注意 Homebrew Python 升级**：Homebrew 升级 Python 小版本时（如 `3.11.15` → `3.11.16`），安装路径中的版本号会变，需重新在"完全磁盘访问"中移除旧条目、添加新路径。可以通过再次运行 `readlink -f ./venv/bin/python` 确认最新路径。

## 7. 维护与调参指南

### 调整搜索严格度

编辑 `config.py` 中的 `SCORE_THRESHOLD`：

- 调小（如 0.35）→ 更严格，只保留高相关结果
- 调大（如 0.60）→ 更宽松，结果更多但可能含噪声

### 增加索引目录

修改 `config.py` 中的 `TARGET_DIR`，然后执行 `python -m everythingsearch.incremental --full` 重建。

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

# 仅运行时环境可改用：
# ./venv/bin/pip install -r requirements/base.txt

# 4. 编辑配置文件
# 必须修改以下内容：
#   - MY_API_KEY: 你的 DashScope API Key
#   - TARGET_DIR: 你要索引的文件目录
#   - MWEB_DIR: MWeb 导出目录（如不用可忽略）
nano config.py

# 5. 构建首次索引
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full

# 6. 启动搜索服务
./scripts/run_app.sh start
# 或开发模式: ./venv/bin/python -m everythingsearch.app
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
LOG_DATE=$(date +%Y-%m-%d)
exec >>"$APP_DIR/logs/launchd_app_${LOG_DATE}.log" 2>&1
exec "$APP_DIR/venv/bin/python" -m gunicorn -c "$APP_DIR/gunicorn.conf.py" \
  -w 1 -b 127.0.0.1:8000 --timeout 120 everythingsearch.app:app
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
LOG_DATE=$(date +%Y-%m-%d)
exec >>"$APP_DIR/logs/incremental_${LOG_DATE}.log" 2>&1
exec "$APP_DIR/venv/bin/python" -m everythingsearch.incremental
EOF
chmod +x ~/.local/bin/everythingsearch_index.sh
cp com.jigger.everythingsearch.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

---

## 9. 版权

© 2026 jiggersong. Licensed under the MIT License.
