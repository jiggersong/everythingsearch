# EverythingSearch Project Manual

[English](PROJECT_MANUAL.en.md) | [中文](PROJECT_MANUAL.md)

## 1. Project Overview

EverythingSearch is a **local semantic file search engine** running on macOS.
It lets users find local documents, code, and materials quickly using natural language or keywords.

### Core Capabilities

- **Hybrid Retrieval Pipeline**: Integrates SQLite FTS5 for sparse retrieval and ChromaDB for dense vector retrieval, using Reciprocal Rank Fusion (RRF) to merge candidate chunks across filenames, headings, and document content without supervision.
- **Intent Recognition & Query Planning**: Employs an LLM to parse natural language search intents dynamically, generating structured query plans with path filters, date ranges, and exact-match fallback constraints.
- **Two-stage Reranking Architecture**: Leverages a remote Rerank model for deep semantic scoring of initial RRF candidates, coupled with a file-level score aggregator to drastically improve Top-K accuracy.
- **Incremental Indexing & Multi-level Caching**: Provides mtime-based incremental file scanning paired with an SQLite persistent cache for embeddings and an in-memory cache for queries, heavily reducing API overhead and latency.
- **Multi-source Data Ingestion**: Features an internal parsing pipeline with asynchronous, cross-process extraction for complex office formats (PDF, Word, Excel, PPT) and seamless auto-synchronization for MWeb Markdown libraries.
- **Privacy & Local-First Design**: Keeps the index and dense vectors entirely local. The model API is only invoked for basic text embeddings and (optionally) for frontend-triggered generative intent or summaries.
- **Agent-Friendly Standardized APIs**: Exposes a highly decoupled, service-oriented RESTful API (complete with strict path-traversal defenses), natively accommodating integration with LLM agents (like Claude or Cursor).

---

## 2. Technical Architecture

```
┌──────────────────────────────────────────────────────┐
│                    WebUI (Browser)                    │
│   index.html · search / filter / sort / paging /      │
│   highlights / reveal in Finder                       │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP (localhost:8000)
┌───────────────────────▼──────────────────────────────┐
│         Flask routing (everythingsearch.app)          │
│   Request validation; unified 400 intercept             │
│   (request_validation)                                │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│             Core service layer (services/)            │
│ SearchService · FileService · HealthService ·         │
│ NLSearchService · SearchInterpretService              │
│ (file_access: unified traversal defense & path        │
│  resolution guard)                                    │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│           Search engine (everythingsearch.search)     │
│   Vector search · position weights · keyword fallback │
│   · per-file dedup · source filter                    │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│            ChromaDB (local vector database)          │
│   collection: local_files · cosine distance           │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│      Indexing (indexer / incremental modules)         │
│   Scan · parse · heading extract · chunk · embed     │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│      Embedding service (embedding_cache module)       │
│   CachedEmbeddings → SQLite cache → DashScope API     │
└──────────────────────────────────────────────────────┘
```

### Technology Stack


| Component       | Choice                                       | Description                                                               |
| --------------- | -------------------------------------------- | ------------------------------------------------------------------------- |
| Language        | Python 3.11                                  | Recommended 3.11 (or 3.10); install dependencies in a virtual environment |
| Orchestration   | LangChain                                    | Document load, chunking, and vectorization pipeline                       |
| Embedding model | Aliyun DashScope text-embedding-v2           | Strong Chinese understanding, low cost                                    |
| Vector database | ChromaDB                                     | Local file-based database; no Docker required                             |
| Web framework   | Flask + Gunicorn                             | Dev / production HTTP service                                             |
| File parsing    | pypdf / python-docx / openpyxl / python-pptx | Extract content from PDF, Word, Excel, PPT                                |
| Frontend        | Single-file HTML + CSS + JS                  | No Node.js build step                                                     |


---

## 3. File Structure

```text
EverythingSearch/
├── config.py                 # Local config (copy from etc/config.example.py; do not commit secrets)
├── etc/
│   └── config.example.py     # Config template
├── everythingsearch/         # Python application package
│   ├── __main__.py           # CLI command dispatcher and app entry point
│   ├── cli.py                # Pure JSON terminal CLI (Agent brain support)
│   ├── app.py                # Flask entry and app assembly
│   ├── services/             # Business service layer (decoupled core logic)
│   │   ├── file_service.py   # File lifecycle control
│   │   ├── search_service.py # Search cache, concurrency, scheduling
│   │   ├── health_service.py # Liveness checks and warmup scheduling
│   │   ├── nl_search_service.py
│   │   └── search_interpret_service.py
│   ├── retrieval/            # ★ Core Multi-way Retrieval and Reranking Pipeline
│   │   ├── pipeline.py       # Main search workflow orchestration
│   │   ├── query_planner.py  # Intent parsing and parameter planning
│   │   ├── sparse_retriever.py # FTS5 sparse retrieval
│   │   ├── dense_retriever.py  # Vector dense retrieval
│   │   ├── fusion.py         # Reciprocal Rank Fusion (RRF)
│   │   ├── reranking.py      # DashScope Rerank integration
│   │   └── aggregation.py    # File-level score aggregation
│   ├── indexing/             # Low-level indexing components
│   │   ├── sparse_index_writer.py
│   │   ├── dense_index_writer.py
│   │   └── pipeline_indexer.py
│   ├── evaluation/           # Search benchmark, dataset loading, and metrics
│   │   ├── benchmark_runner.py
│   │   ├── dataset.py
│   │   ├── metrics.py
│   │   └── datasets/
│   ├── infra/                # Infrastructure layer (incl. strongly typed settings.py)
│   ├── request_validation.py # Input validation protocol (unified HTTP 400 contract)
│   ├── file_access.py        # Strict file access boundary; anti path traversal
│   ├── indexer.py            # Full index build entrypoint
│   ├── incremental.py        # Incremental indexing entrypoint
│   ├── embedding_cache.py    # Embedding cache layer
│   ├── logging_config.py     # Standardized logging configuration
│   ├── templates/            # Web UI templates
│   │   └── index.html
│   └── static/               # Frontend static assets
│       ├── css/
│       ├── js/
│       └── icon.png
├── skills/                   # Agent Skill (supports Cursor/Claude for local API integration)
├── data/                     # Local data and cache (default paths; do not commit)
│   ├── chroma_db/            # ChromaDB vector store
│   ├── sparse_index.db       # FTS5 sparse index database
│   ├── embedding_cache.db
│   ├── scan_cache.db
│   └── index_state.db
├── logs/                     # Runtime and scheduled job logs
├── scripts/                  # Operations and helper scripts
│   ├── install.sh
│   ├── run_app.sh
│   ├── audit_dependencies.py # Dependency audit utility
│   └── mweb_export.py        # MWeb automatic export wrapper
├── docs/                     # Project documentation
│   ├── CHANGELOG.md          # Changelog
│   ├── INSTALL.md            # Deployment & Installation Guide
│   ├── PROJECT_MANUAL.md     # Technical Architecture Document (this file)
│   ├── NL_SEARCH_AND_WEB_UI.md # Smart Retrieval Mechanisms Explained
│   ├── SEARCH_ACCURACY_TECHNICAL_DESIGN.md # Accuracy-first search redesign docs
│   └── UI_DESIGN_APPLE_GOOGLE.md # UI design philosophy
├── Makefile                  # make shortcuts
├── requirements/             # Dependency lists
├── pytest.ini                # Unit test config
└── tests/                    # Unit tests and evaluation cases

~/.local/bin/
├── everythingsearch_start.sh  # App launchd wrapper (created at install)
└── everythingsearch_index.sh  # Incremental index launchd wrapper (created at install)
```

### 3.1 Agent Skill

For **Cursor, Claude Code, and other tools that support Agent Skills**, this repository ships a versioned Skill file at the repo root:


| Item          | Description                                                                                                                                                                                                               |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Path**      | `skills/everythingsearch-local/SKILL.md`                                                                                                                                                                                  |
| **Contents**  | How to call the local HTTP API for hybrid search, natural-language intent search, intelligent result interpretation, text read / file download, etc.—aligned with `docs/NL_SEARCH_AND_WEB_UI.en.md` and §4.6 routes below |
| **Base URL**  | Defaults to `http://127.0.0.1:8000`. If the service listens elsewhere, set `EVERYTHINGSEARCH_BASE` in the agent environment (must include the scheme, e.g. `http://127.0.0.1:8000`)                                       |
| **DashScope** | NL and interpretation routes require a valid API key on the server; without a key, the Skill recommends falling back to `GET /api/search`—see the Skill preamble                                                          |


To use this Skill in Cursor, **copy** `skills/everythingsearch-local/` to `.cursor/skills/everythingsearch-local/` in your workspace, or create a **symbolic link** there pointing at the in-repo folder, then reload skills per your tool’s docs.

### 3.2 CLI Terminal Interface

To support LLM Agents that lack independent HTTP request capabilities (such as local agent environments like OpenClaw), the project provides a command-line tool that outputs pure JSON:

```bash
python -m everythingsearch search "<query>" --json
```

- This interface shares the exact same intent recognition and hybrid retrieval pipeline as the Web frontend's natural language search.
- It internally suppresses redundant terminal outputs from third-party libraries (like `jieba` dictionary loading) to ensure the Agent can successfully parse the JSON content from `stdout`.
- For complete integration guides and system prompt examples, please see `docs/OPENCLAW_INTEGRATION.md`.

---

## 4. Core Module Details

### 4.1 `config.py` — Configuration hub

Local settings are concentrated here. Load order: environment variables > repository-root `config.py` > safe in-code defaults.


| Key                            | Default                                        | Description                                                                                         |
| ------------------------------ | ---------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `MY_API_KEY`                   | empty string or `DASHSCOPE_API_KEY` env var    | Legacy-compatible Alibaba Tongyi DashScope API key field; prefer environment variables              |
| `TARGET_DIR`                   | `/path/to/documents` or `["/path1", "/path2"]` | Root directory or list of roots to index; `TARGET_DIR` env var wins                                 |
| `ENABLE_MWEB`                  | `False` / `True`                               | One-switch seamless built-in MWeb note integration; when on, the system takes over automatic export |
| `MWEB_LIBRARY_PATH`            | Default macOS library path                     | MWeb main database directory (optional override)                                                    |
| `MWEB_DIR`                     | `data/mweb_export`                             | Managed export landing zone for MWeb notes                                                          |
| `INDEX_STATE_DB`               | `./index_state.db`                             | Incremental indexing state database                                                                 |
| `SCAN_CACHE_PATH`              | `./scan_cache.db`                              | Scan/parse cache (skip unchanged files)                                                             |
| `EMBEDDING_MODEL`              | `text-embedding-v2`                            | Embedding model name                                                                                |
| `CHUNK_SIZE`                   | `500`                                          | Text chunk size (characters)                                                                        |
| `CHUNK_OVERLAP`                | `80`                                           | Chunk overlap (characters)                                                                          |
| `MAX_CONTENT_LENGTH`           | `20000`                                        | Max characters indexed per file                                                                     |
| `SEARCH_TOP_K`                 | `250`                                          | Vector retrieval candidate chunks (higher = more recall, slower)                                    |
| `SCORE_THRESHOLD`              | `0.35`                                         | Cosine distance threshold (smaller = stricter; matches `settings.py` default)                       |
| `POSITION_WEIGHTS`             | `filename:0.6, heading:0.8, content:1.0`       | Position weighting factors                                                                          |
| `KEYWORD_FREQ_BONUS`           | `0.03`                                         | Keyword frequency bonus coefficient                                                                 |
| `TRUST_PROXY`                  | `False`                                        | Trust `X-Forwarded-For` from a reverse proxy (for per-IP rate limiting)                             |
| `NL_INTENT_MODEL`              | `qwen-turbo`                                   | NL intent model (prefer JSON Mode–capable models)                                                   |
| `SEARCH_INTERPRET_MODEL`       | `qwen-turbo`                                   | Model for optional “smart interpretation” of hit lists                                              |
| `NL_TIMEOUT_SEC`               | `10`                                           | Intent call timeout (seconds)                                                                       |
| `INTERPRET_TIMEOUT_SEC`        | `20`                                           | Interpretation call timeout (seconds)                                                               |
| `NL_MAX_MESSAGE_CHARS`         | `1000`                                         | Max characters per intent request                                                                   |
| `INTERPRET_MAX_RESULTS`        | `10`                                           | Max hits summarized in interpretation                                                               |
| `RATE_LIMIT_NL_PER_MIN`        | `10`                                           | Per-IP requests/minute for `POST /api/search/nl`                                                    |
| `RATE_LIMIT_INTERPRET_PER_MIN` | `10`                                           | Per-IP requests/minute for interpretation endpoints                                                 |


**API key best practices**

- Prefer `DASHSCOPE_API_KEY` in the environment instead of a real key in `config.py` (especially when copying the project to another machine)
- The template does not ship a runnable fake default; empty means “not configured,” not an error by itself
- Without a key: **incremental/full indexing cannot embed** (embeddings require DashScope). The **web UI** falls back to `GET /api/search` only (no intent or interpretation). If the vector DB is also unavailable, search may still error until indexing succeeds with a valid key.
- The legacy `NL_SEARCH_ENABLED` toggle is removed: when a key is configured, the web UI uses the NL pipeline by default (intent + hybrid search + optional interpretation). See `docs/NL_SEARCH_AND_WEB_UI.md`.

### 4.2 `indexer.py` — Index builder

**File scan**: Recursively walks `TARGET_DIR` (supports multiple roots), classifying by extension:

- **Text** (`.txt`, `.md`, `.py`, …): read directly
- **Office** (`.pdf`, `.docx`, `.xlsx`, `.pptx`): parsed in a subprocess (avoids C-extension deadlocks; 30s timeout)
- **Media** (`.jpg`, `.mp4`, …): filename only

**Heading extraction**: Titles/headings become their own chunks and receive ranking weight in search.

**Full-index batch sizing**: `calculate_batch_size(docs)` picks batch size from average `page_content` length (roughly 25 / 40 / 55 for long / medium / short docs) to balance API throughput and payload size.

**MWeb notes**: Parses YAML front matter (`title`, `categories`, `mweb_uuid`), extracts Markdown headings, same chunk layout as files.

**Three chunk types per file**:

1. `chunk_type: "filename"` — filename + path summary
2. `chunk_type: "heading"` — extracted headings
3. `chunk_type: "content"` — body chunks (~500 characters each)

### 4.3 `retrieval.pipeline` — Multi-way Retrieval and Reranking Engine

The core search engine follows a multi-stage retrieval architecture:

```text
SearchRequest
  -> QueryPlanner
  -> SparseRetriever (SQLite FTS5)
  -> DenseRetriever (Embedding / Chroma adapter)
  -> CandidateFusion (RRF)
  -> Reranker (DashScope qwen3-rerank provider)
  -> FileAggregator
  -> ResultPresenter
```

**Timeout and Busy Protection**:
Search execution is protected at the business layer via concurrency control and a timeout wrapper (`SEARCH_TIMEOUT_SECONDS`, default 30s). Timeouts or busy states bubble up and are converted to 504/503 HTTP responses.

**Core Pipeline Stages**:

1. **Query Planner**: Generates a structured `QueryPlan` from the frontend request (including optional `path_filter`, `date_field`, etc.). If `exact_focus` is specified, it gracefully degrades to a keyword-focused hybrid mode.
2. **Sparse Retriever**: Performs rapid inverted index queries using the newly added `data/sparse_index.db` (SQLite FTS5). Field weighting is governed by configuration keys like `SPARSE_FILENAME_WEIGHT` and `SPARSE_PATH_WEIGHT`.
3. **Dense Retriever**: Computes semantic similarity to extract candidate chunks using the existing ChromaDB and Embedding layer.
4. **Candidate Fusion (RRF)**: Applies Reciprocal Rank Fusion to combine sparse and dense results without supervision.
5. **Reranker (Second-stage Ranking)**: If `RERANK_MODEL` (e.g., DashScope's qwen3-rerank) is configured, the Top N candidates from RRF are sent to the reranking model for deep semantic scoring. Defaults to RRF scores if the reranker times out or degrades.
6. **File Aggregator**: Replaces the previous "highest-scoring chunk per file" approach with a file-level score aggregation across all candidate chunks, yielding a much more accurate final ranking.

### 4.4 `embedding_cache.py` — Embedding cache

`CachedEmbeddings` subclasses `DashScopeEmbeddings` and checks SQLite before calling the API:

- Key: `SHA256(model_name + "::" + text)`
- Value: JSON-serialized vector; `created_at` (Unix timestamp) on write
- **WAL** mode and a **connection pool** (fixed pool size); legacy two-column tables get `created_at` via `ALTER TABLE`
- Hit/call counters use `PrivateAttr` + `threading.Lock` so Pydantic defaults do not deep-copy badly
- After the first full index, later rebuilds rarely need API calls

### 4.5 `everythingsearch.incremental` — Incremental indexing

SQLite table `file_index` tracks `(filepath, mtime, source_type)`:

- **New file**: embed and write to ChromaDB  
- **Modified** (mtime changed): delete old chunks, reindex  
- **Deleted** (missing on disk): remove from ChromaDB and state table  
- **Unchanged**: skip

**MWeb toggle**:

- `ENABLE_MWEB = False`: no export script, no MWeb directory scan, no MWeb source on the search UI

Run:

```bash
python -m everythingsearch.incremental          # incremental
python -m everythingsearch.incremental --full   # full rebuild
# or from repo root:
./venv/bin/python everythingsearch/incremental.py
```

> After indexing, restart the search service to load new data: `./scripts/run_app.sh restart`

### 4.6 `everythingsearch.app` and service layer

`app.py` focuses exclusively on routing and HTTP interface definitions, delegating all core business logic to the `services/` layer. Coupled with `request_validation.py`, it intercepts invalid JSON and malformed parameters, returning standardized `400 Bad Request` responses to prevent dirty data from causing system-level 500 crashes. Additionally, `file_access.py` provides a strict isolation boundary, enforcing that all read, download, or open operations are securely contained within indexed directories to prevent path traversal vulnerabilities.

**Agent integration**: For Cursor and similar tools, HTTP examples, `EVERYTHINGSEARCH_BASE`, and no-key fallback notes live in §3.1 — `skills/everythingsearch-local/SKILL.md`.

Routes:

- `GET /` — search page (`smart_search_available` in the template: DashScope key configured → browser uses `POST /api/search/nl`; otherwise `GET /api/search`)  
- `GET /api/search?q=...&source=all|file|mweb` — direct search (optional `date_field` / `date_from` / `date_to` / `limit=1..200`; **no** LLM intent)  
- `POST /api/search/nl` — NL search: DashScope intent JSON → `SearchService.search` (optional `exact_focus`); requires API key and reachable model endpoint  
- `POST /api/search/interpret`, `POST /api/search/interpret/stream` — short “smart interpretation” over the current hit list; requires API key; per-IP rate limits apply  
- `GET /api/health` — health payload; if `vectordb.status` is not `"ok"`, top-level `ok` is strictly `false` for monitoring consistency  
- `POST /api/cache/clear` — clear **in-memory** search cache  
- `GET /api/file/read?filepath=...` — read text from a file **under indexed roots**  
- `GET /api/file/download?filepath=...` — download a file **under indexed roots**  
- `POST /api/reveal` — show file in Finder  
- `POST /api/open` — open file with default app

> For security, these are **not** exposed: `/api/config`, `/api/stats`, `/api/reload`.  
> After rebuilding the index, restart the search service: `./scripts/run_app.sh restart`

**How to run**

- Dev: `./venv/bin/python -m everythingsearch.app` or `./scripts/run_app.sh dev`  
- Daemon: `./scripts/run_app.sh start` (gunicorn background)  
- Control: `./scripts/run_app.sh stop|restart|status`

### 4.7 launchd background services

> **macOS TCC**: On macOS Ventura and later, `~/Documents` is protected. LaunchAgent processes **cannot** use scripts, `WorkingDirectory`, or log paths under that tree directly. Plists therefore call wrapper scripts in `~/.local/bin/`—bash `cd`s into the project and starts gunicorn or incremental indexing. `StandardOutPath` / `StandardErrorPath` in the plist point at `/tmp/`; application logs still go to `logs/` via gunicorn.

**Search service** (`com.jigger.everythingsearch.app.plist`):

- `RunAtLoad` + `KeepAlive`: start at login, restart on crash  
- `~/.local/bin/everythingsearch_start.sh` starts gunicorn on port 8000

**Scheduled indexing** (`com.jigger.everythingsearch.plist`):

- Runs incremental indexing every **30 minutes**; runs after wake if a run was missed  
- `~/.local/bin/everythingsearch_index.sh` runs `python -m everythingsearch.incremental`

**Management** (prefer `launchctl bootstrap` / `bootout` over legacy `load` / `unload`):

```bash
# Status
launchctl list | grep everythingsearch

# Reload search service
launchctl bootout gui/$(id -u)/com.jigger.everythingsearch.app
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist

# Reload scheduled indexing
launchctl bootout gui/$(id -u)/com.jigger.everythingsearch
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

---

## 5. Dependencies

### External services

- **Alibaba Cloud DashScope API**: requires a valid API key  
  - **Embeddings**: `text-embedding-v2` by default, used during indexing  
  - **Generative** (optional): web `POST /api/search/nl` and interpretation endpoints use `NL_INTENT_MODEL` / `SEARCH_INTERPRET_MODEL` (default `qwen-turbo`); those calls need outbound network  
  - Sign up → enable DashScope → create an API key  
  - Cost is very low for embeddings (about ¥0.0007 / 1000 tokens); intent/interpretation billed per model

### Local resources

- macOS 10.15+  
- Python 3.10 or 3.11 (3.11 recommended)  
- ~500MB disk (venv + databases)  
- Network: required for indexing (embeddings); `GET /api/search` can be offline once vectors exist; NL search and interpretation require network access to DashScope

---

## 6. Daily usage

### Makefile shortcuts

```bash
cd /path/to/EverythingSearch
make help          # list all make targets with one-line descriptions
make index         # incremental index
make index-full    # full rebuild
make app           # foreground app
make app-status    # launchd service status
make app-restart   # restart launchd service
make app-stop      # stop launchd service
```

Keep `make help` in sync with the root `Makefile` `help` target; run `make help` when you forget a subcommand.

### Start the search service

```bash
cd /path/to/EverythingSearch
# Option A: dev (foreground)
./venv/bin/python -m everythingsearch.app
# or ./scripts/run_app.sh dev

# Option B: daemon (background, restartable)
./scripts/run_app.sh start
./scripts/run_app.sh status
./scripts/run_app.sh restart
./scripts/run_app.sh stop
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser.

### Manual incremental index

```bash
cd /path/to/EverythingSearch
./venv/bin/python -m everythingsearch.incremental
# After indexing, restart to load new data
./scripts/run_app.sh restart
```

### Full rebuild (first time or after large changes)

```bash
cd /path/to/EverythingSearch
caffeinate -i nohup ./venv/bin/python -m everythingsearch.incremental --full >> "logs/full_rebuild_$(date +%Y-%m-%d).log" 2>&1 &
# After indexing, restart the search service to load new data
# ./scripts/run_app.sh restart
```

`caffeinate -i` prevents sleep from killing the job.

### Incremental index logs

```bash
# Daily file: incremental_YYYY-MM-DD.log (stdout/stderr merged)
ls -1 logs/incremental_*.log
tail -n 200 logs/incremental_$(date +%Y-%m-%d).log
```

### 6.5 System permissions and automation

Configure login auto-start, scheduled incremental indexing, and stop repeated “Python wants to access…” dialogs for background jobs.

#### Auto-start (search service)

Uses launchd `RunAtLoad + KeepAlive`. `install.sh` typically:

1. Writes `~/.local/bin/everythingsearch_start.sh`
2. Copies `com.jigger.everythingsearch.app.plist` to `~/Library/LaunchAgents/`
3. Registers with `launchctl bootstrap`

After registration, the service starts at login and restarts if it crashes.

**Manual registration (e.g. new machine)**:

```bash
mkdir -p ~/.local/bin
cp scripts/launchd/com.jigger.everythingsearch.app.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist

launchctl list | grep everythingsearch
```

> **Why wrappers instead of paths in the plist?**  
> TCC blocks LaunchAgents from putting `~/Documents/` in `WorkingDirectory`, `StandardOutPath`, etc. Wrappers live in `~/.local/bin/`, run under bash, then `cd` into the project.

#### Scheduled indexing (automatic incremental updates)

`com.jigger.everythingsearch.plist` runs incremental indexing every **30 minutes** by default; missed runs execute after wake.

**Manual registration**:

```bash
mkdir -p ~/.local/bin
cp scripts/launchd/com.jigger.everythingsearch.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

**Change schedule (example: 08:30)**:

```bash
nano ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
# Edit Hour and Minute

launchctl bootout gui/$(id -u)/com.jigger.everythingsearch
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist

launchctl list | grep everythingsearch
```

#### Full Disk Access (stop permission popups)

**Symptom**: Each scheduled run shows “python3.11 wants to access data from other apps” until you click Allow.

**Cause**: launchd runs Python in the background; TCC blocks protected locations (e.g. MWeb under `~/Library/...`) until you grant Full Disk Access.

**Fix**

Resolve the real interpreter:

```bash
readlink -f ./venv/bin/python
# e.g. /opt/homebrew/Cellar/python@3.11/3.11.15/Frameworks/Python.framework/Versions/3.11/bin/python3.11
```

In **System Settings → Privacy & Security → Full Disk Access**:

1. Click **+**
2. `Cmd+Shift+G`, paste the path above, **Open**
3. Add `/bin/bash` as well (launchd invokes bash → wrapper)
4. Enable both toggles

After that, scheduled indexing runs quietly.

> **Homebrew Python upgrades**: Patch bumps (e.g. `3.11.15` → `3.11.16`) change the path—remove the old Full Disk Access entry and add the new path from `readlink -f ./venv/bin/python`.

---

## 7. Maintenance and tuning

### Search strictness

Edit `SCORE_THRESHOLD` in `config.py`:

- Lower (e.g. `0.35`) → stricter, higher-precision set  
- Higher (e.g. `0.60`) → more results, more noise

### More roots

Change `TARGET_DIR`, then `python -m everythingsearch.incremental --full`.

### Different embedding model

Set `EMBEDDING_MODEL` to a DashScope-supported name, then full rebuild; cache keys include the model name.

### Cron / plist schedule

1. Edit `Hour` / `Minute` in `com.jigger.everythingsearch.plist`
2. Reload:

```bash
launchctl bootout gui/$(id -u)/com.jigger.everythingsearch
cp scripts/launchd/com.jigger.everythingsearch.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

### New file types

Add extensions in `config.py` (`TEXT_EXTENSIONS`, `OFFICE_EXTENSIONS`, `MEDIA_EXTENSIONS`); add a branch in `indexer.py` `_read_file_worker` if a custom parser is needed.

---

## 8. Fresh deployment checklist

For a brand-new Mac.

### Prerequisites

- macOS 10.15+  
- Homebrew (if missing: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`)  
- DashScope API key

### Steps

```bash
# 1. Install Python 3.11
brew install python@3.11

# 2. Place the project (e.g. tarball)
mkdir -p ~/Documents/code
cd ~/Documents/code
tar xzf /path/to/EverythingSearch.tar.gz

# 3. Virtualenv and dependencies
cd EverythingSearch
python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt

# Runtime-only option:
# ./venv/bin/pip install -r requirements/base.txt

# 4. Edit config — at minimum:
#    MY_API_KEY: your DashScope API key
#    TARGET_DIR: directories to index
#    MWEB_DIR: MWeb export dir (ignore if unused)
nano config.py

# 5. First full index
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full

# 6. Start search service
./scripts/run_app.sh start
# or dev: ./venv/bin/python -m everythingsearch.app
# Browser: http://127.0.0.1:8000

# 7. (Optional) Auto-start at login
#     TCC: LaunchAgent cannot point straight at ~/Documents; use ~/.local/bin wrappers.
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
cp scripts/launchd/com.jigger.everythingsearch.app.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist

# 8. (Optional) Scheduled incremental indexing
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
cp scripts/launchd/com.jigger.everythingsearch.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

---

## 9. Copyright

© 2026 jiggersong. Licensed under the MIT License.
