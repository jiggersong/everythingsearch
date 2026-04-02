# EverythingSearch Project Manual

[English](PROJECT_MANUAL.en.md) | [中文](PROJECT_MANUAL.md)

## 1. Project Overview

EverythingSearch is a **local semantic file search engine** running on macOS.
It allows users to quickly find local documents, code, and knowledge files using natural language or keywords.

### Core Capabilities

- **Semantic search**: understands intent beyond exact keyword matching
- **Hybrid indexing**: indexes both file content and filenames, so media files can still be found by name
- **Seamless MWeb Integration (Optional)**: Enable built-in MWeb note syncing with a single switch. Fully managed extraction and retrieval labeled in UI; disable entirely with `ENABLE_MWEB=False`
- **Position weighting**: keywords in filename/headings receive higher ranking
- **Embedding cache**: avoids repeated API embedding calls; SQLite uses WAL and connection pooling
- **Incremental indexing**: updates only new/modified/deleted files on each run
- **Search memory cache and health API**: repeated queries can hit memory cache; includes `/api/health` and `POST /api/cache/clear`
- **Privacy-first with controlled cloud usage**: index and vector DB stay local (ChromaDB); cloud API is used only for embedding generation
- **Web UI**: source filter, sorting, pagination, highlights, Finder reveal

---

## 2. Technical Architecture

```
┌──────────────────────────────────────────────────────┐
│                    WebUI (Browser)                    │
│   index.html · search/filter/sort/paging/highlight    │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP (localhost:8000)
┌─────────────────────────▼────────────────────────────┐
│         Flask Routing System (everythingsearch.app)  │
│ Request validation / 400 intercept (request_validation)│
└─────────────────────────┬────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────┐
│             Core Service Layer (services/)           │
│         SearchService · FileService · HealthService  │
│        (Strict file_access / traversal defense)      │
└─────────────────────────┬────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────┐
│            Search Engine (everythingsearch.search)   │
│  vector search · position weight · keyword fallback   │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│            ChromaDB (local vector database)           │
│  collection: local_files · cosine distance            │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│      Indexing (indexer / incremental modules)         │
│  scan · parse · heading extract · chunk · embedding   │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│      Embedding Service (embedding_cache module)       │
│  CachedEmbeddings -> SQLite cache -> DashScope API    │
└──────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Choice | Description |
|-----------|--------|-------------|
| Language | Python 3.11 | Recommended 3.11 (or 3.10); use virtualenv |
| Orchestration | LangChain | Document load/chunk/vector pipeline |
| Embedding model | Aliyun DashScope text-embedding-v2 | Strong Chinese understanding, low cost |
| Vector database | ChromaDB | Local file-based DB, no Docker required |
| Web framework | Flask + Gunicorn | Dev/prod HTTP service |
| File parsing | pypdf / python-docx / openpyxl / python-pptx | Parse PDF/Word/Excel/PPT |
| Frontend | Single HTML + CSS + JS file | No Node.js build required |

---

## 3. File Structure

```text
EverythingSearch/
├── config.py                 # Local config (copied from etc/config.example.py)
├── etc/
│   └── config.example.py     # Config template
├── everythingsearch/         # Python application package
│   ├── app.py                # Flask web routing entry
│   ├── services/             # Core service layer (abstracting business logic)
│   │   ├── file_service.py   # File lifecycle & access control
│   │   ├── search_service.py # Search cache & concurrency
│   │   └── health_service.py # Health & warmup orchestration
│   ├── request_validation.py # Request logic parsing (unified HTTP 400 rules)
│   ├── file_access.py        # Strict file access boundary & anti-traversal
│   ├── infra/                # Infrastructure layer
│   │   ├── settings.py       # (typed config injection)
│   ├── search.py             # Base search engine algorithm
│   ├── indexer.py            # Full indexing
│   ├── incremental.py        # Incremental indexing
│   ├── embedding_cache.py    # Embedding cache layer
│   ├── templates/
│   │   └── index.html
│   └── static/
│       └── icon.png
├── data/                     # Local data/cache (default paths, do not commit)
│   ├── chroma_db/            # ChromaDB
│   ├── embedding_cache.db
│   ├── scan_cache.db
│   └── index_state.db
├── logs/                     # Runtime and scheduled task logs
├── scripts/
│   ├── install.sh
│   ├── run_app.sh            # Service management (start/stop/restart/dev)
│   ├── run_tests.sh
│   └── launchd/              # launchd plist reference copies
├── docs/
│   ├── INSTALL.en.md
│   ├── PROJECT_MANUAL.en.md
│   ├── UI_DESIGN_APPLE_GOOGLE.en.md   # Web UI design notes (English)
│   └── UI_DESIGN_APPLE_GOOGLE.md      # Web UI design notes (Chinese)
├── Makefile                  # make shortcuts (make help lists targets)
├── requirements.txt
├── requirements/
│   ├── base.txt
│   └── dev.txt
├── pytest.ini
├── tests/
└── venv/

~/.local/bin/
├── everythingsearch_start.sh  # launchd wrapper for app service
└── everythingsearch_index.sh  # launchd wrapper for incremental indexing
```

---

## 4. Core Module Details

### 4.1 `config.py` - Configuration Center

Local compatibility settings mainly live in this file; runtime load order is: environment variables > repository-root `config.py` > safe in-code defaults.

| Key | Default | Description |
|-----|---------|-------------|
| `MY_API_KEY` | empty string or `DASHSCOPE_API_KEY` env var | Legacy-compatible DashScope API key field; prefer env var first |
| `TARGET_DIR` | `/path/to/documents` or `["/path1", "/path2"]` | Root directory/directories to index; `TARGET_DIR` env var takes precedence |
| `ENABLE_MWEB` | `False/True` | Enables seamless built-in MWeb engine integration for automatic exports. |
| `MWEB_LIBRARY_PATH`| macOS default path | [Optional] Target MWeb DB path (fallback for gigks) |
| `MWEB_DIR` | `data/mweb_export` | Fully managed internal extraction vault |
| `INDEX_STATE_DB` | `./index_state.db` | Incremental state database |
| `SCAN_CACHE_PATH` | `./scan_cache.db` | Scan/parse cache DB |
| `EMBEDDING_MODEL` | `text-embedding-v2` | Embedding model |
| `CHUNK_SIZE` | `500` | Text chunk size (chars) |
| `CHUNK_OVERLAP` | `80` | Chunk overlap (chars) |
| `MAX_CONTENT_LENGTH` | `20000` | Max indexed chars per file |
| `SEARCH_TOP_K` | `250` | Candidate chunks from vector retrieval |
| `SCORE_THRESHOLD` | `0.45` | Cosine distance threshold (smaller = stricter) |
| `POSITION_WEIGHTS` | `filename:0.6, heading:0.8, content:1.0` | Position weighting factors |
| `KEYWORD_FREQ_BONUS` | `0.03` | Keyword frequency bonus |

**API key recommendation**:
- Prefer environment variable `DASHSCOPE_API_KEY` over hardcoding key in file
- The template no longer ships with a runnable placeholder secret; empty means "not configured"
- Missing key intentionally causes clear startup/indexing errors

### 4.2 `indexer.py` - Index Builder

**File scan** recursively walks `TARGET_DIR` and categorizes by extension:
- **Text files** (`.txt`, `.md`, `.py`, etc.): direct read
- **Office files** (`.pdf`, `.docx`, `.xlsx`, `.pptx`): subprocess parser (30s timeout)
- **Media files** (`.jpg`, `.mp4`, etc.): filename-only indexing

**Heading extraction** stores headings as independent chunks for ranking bonus.

**Batch sizing for full indexing**: `calculate_batch_size(docs)` adapts batch size by average content length (roughly 25 / 40 / 55).

**MWeb note scan** parses YAML front matter (`title`, `categories`, `mweb_uuid`) and heading structure similarly to files.

**Each file generates 3 chunk types**:
1. `chunk_type: "filename"` - filename + path summary
2. `chunk_type: "heading"` - extracted headings
3. `chunk_type: "content"` - body chunks (~500 chars each)

### 4.3 `search.py` - Search Engine

**Memory cache**: caches results by `(query, source_filter, date_field, date_from, date_to)`; clear via `POST /api/cache/clear` when immediate consistency is needed.

**Timeout control**: search execution is wrapped in a shared in-process future-based timeout guard, using `SEARCH_TIMEOUT_SECONDS = 30` by default. A timeout is no longer treated as an empty result; it is surfaced as an observable error (`/api/search` returns HTTP 504). Timed-out searches are not written into the in-memory cache. Setting `SEARCH_TIMEOUT_SECONDS = 0` disables timeout enforcement, but single-flight execution and busy protection still remain in effect. Note that a future timeout does not forcibly kill an already running worker thread; the background task may continue until it finishes naturally. While that background task is still draining, new search requests may receive an HTTP 503 "busy" response to avoid unbounded task buildup.

Search pipeline:
1. **Vector retrieval** in one collection with source filter (`all|file|mweb`)
2. **Position weighting** by `chunk_type`
3. **Keyword frequency bonus**
4. **File-level deduplication**
5. **Keyword exact fallback** using ChromaDB `$contains`
6. **Merge and rerank**

### 4.4 `embedding_cache.py` - Embedding Cache

`CachedEmbeddings` extends `DashScopeEmbeddings` and checks SQLite before API call:
- Key: `SHA256(model_name + "::" + text)`
- Value: JSON-serialized vector with `created_at` timestamp
- Uses **WAL** and **connection pool**
- Legacy two-column schema auto-migrates with `ALTER TABLE` to add `created_at`
- Hit/call counters use `PrivateAttr` + lock for safety

### 4.5 `everythingsearch.incremental` - Incremental Indexing

Tracks `(filepath, mtime, source_type)` in `file_index`:
- **new file**: index and insert
- **modified file**: delete old chunks then reindex
- **deleted file**: remove from ChromaDB and state DB
- **unchanged file**: skip

**MWeb optional switch**:
- With `ENABLE_MWEB=False`, no MWeb export/scan is executed

Run modes:
```bash
python -m everythingsearch.incremental          # incremental update
python -m everythingsearch.incremental --full   # full rebuild
# or (from repo root):
./venv/bin/python everythingsearch/incremental.py
```

> After indexing, restart app to load fresh data: `./scripts/run_app.sh restart`

### 4.6 `everythingsearch.app` & Service Orchestration

Recent updates significantly slimmed down `app.py`. It delegates core business logic to the `services/` layer and uses `request_validation.py` to filter all invalid JSON payloads directly into standard HTTP `400 Bad Request` responses, preventing 500 crashes. The underlying `file_access.py` adds a strict boundary: any external read/download/open action is forcefully restricted from traversing outside the indexed directories.

Flask routes remain consistent:
- `GET /` - main page
- `GET /api/search?q=...&source=all|file|mweb` - search API (`limit=1..200` optional)
- `GET /api/health` - State summary. If `vectordb.status` goes degraded, the top-level `ok` flag strictly returns `false` to maintain explicit monitoring consistency.
- `POST /api/cache/clear` - clear in-memory search cache
- `GET /api/file/read?filepath=...` - read text content of files **within indexed roots**
- `GET /api/file/download?filepath=...` - download a file **within indexed roots**
- `POST /api/reveal` - reveal file in Finder (secure path validation applied)
- `POST /api/open` - open file with default app (secure path validation applied)

> Intentionally not provided for security: `/api/config`, `/api/stats`, `/api/reload`.

Run modes:
- Dev: `./venv/bin/python -m everythingsearch.app` or `./scripts/run_app.sh dev`
- Background: `./scripts/run_app.sh start` (gunicorn)
- Management: `./scripts/run_app.sh stop|restart|status`

### 4.7 launchd Background Services

> **macOS TCC limitation**: LaunchAgent cannot directly access scripts/log paths under `~/Documents` on newer macOS versions.
> Wrapper scripts under `~/.local/bin/` are used to `cd` into project and start gunicorn/incremental jobs.

**App service** (`com.jigger.everythingsearch.app.plist`):
- `RunAtLoad` + `KeepAlive`
- Starts gunicorn via `~/.local/bin/everythingsearch_start.sh`

**Scheduled indexing** (`com.jigger.everythingsearch.plist`):
- runs daily at 10:00
- starts `python -m everythingsearch.incremental` via wrapper

**Management commands**:
```bash
launchctl list | grep everythingsearch
launchctl bootout gui/$(id -u)/com.jigger.everythingsearch.app
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist
launchctl bootout gui/$(id -u)/com.jigger.everythingsearch
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

---

## 5. Dependencies

### External Service
- **DashScope API** for embeddings (`text-embedding-v2`)
  - obtain by creating API key in DashScope console
  - cost is low (about RMB 0.0007 / 1000 tokens)

### Local Resources
- macOS 10.15+
- Python 3.10/3.11 (3.11 recommended)
- ~500MB disk space for venv and local DBs
- internet required only during indexing (embedding API calls)

---

## 6. Daily Usage

### Makefile shortcuts
```bash
cd /path/to/EverythingSearch
make help          # list all make targets with one-line descriptions
make index
make index-full
make app
make app-status
make app-restart
make app-stop
```

`make help` is defined in the root `Makefile` and should stay in sync with available targets; use it when you forget command names.

### Start search service
```bash
cd /path/to/EverythingSearch
./venv/bin/python -m everythingsearch.app
# or ./scripts/run_app.sh dev
./scripts/run_app.sh start
./scripts/run_app.sh status
./scripts/run_app.sh restart
./scripts/run_app.sh stop
```

### Manual incremental indexing
```bash
cd /path/to/EverythingSearch
./venv/bin/python -m everythingsearch.incremental
./scripts/run_app.sh restart
```

### Full rebuild
```bash
cd /path/to/EverythingSearch
caffeinate -i nohup ./venv/bin/python -m everythingsearch.incremental --full >> "logs/full_rebuild_$(date +%Y-%m-%d).log" 2>&1 &
```

### View incremental logs
```bash
ls -1 logs/incremental_*.log
tail -n 200 logs/incremental_$(date +%Y-%m-%d).log
```

### 6.5 System Permissions & Automation Setup

This section explains how to configure auto-start on login, scheduled daily indexing, and how to resolve the macOS permission dialog that appears when Python runs as a background process.

#### Auto-start on Login (Search Service)

The search service uses launchd's `RunAtLoad + KeepAlive` mechanism to start automatically after login. The installer (`install.sh`) handles this automatically:

1. Generates `~/.local/bin/everythingsearch_start.sh` wrapper script
2. Copies `com.jigger.everythingsearch.app.plist` to `~/Library/LaunchAgents/`
3. Registers the service via `launchctl bootstrap`

Once registered, the service starts on every login and restarts automatically if it crashes.

**Manual registration (e.g. after migrating to a new machine)**:
```bash
mkdir -p ~/.local/bin
cp scripts/launchd/com.jigger.everythingsearch.app.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist

# Verify registration
launchctl list | grep everythingsearch
```

> **Why use wrapper scripts instead of direct paths in the plist?**  
> macOS TCC (Transparency, Consent, and Control) prevents LaunchAgents from using `~/Documents/` paths in plist fields such as `WorkingDirectory` or `StandardOutPath`. The wrapper scripts live in `~/.local/bin/` (unrestricted), and internally `cd` into the project directory before launching gunicorn or Python.

#### Scheduled Indexing (Daily Automatic Incremental Update)

Incremental indexing is controlled by `com.jigger.everythingsearch.plist` and runs daily at **10:00 AM** by default. If the Mac is asleep at that time, launchd will execute the task the next time the machine wakes up.

**Manual registration**:
```bash
mkdir -p ~/.local/bin
cp scripts/launchd/com.jigger.everythingsearch.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

**Change schedule time** (e.g. to 8:30 AM):
```bash
# 1. Edit the plist — update Hour and Minute values
nano ~/Library/LaunchAgents/com.jigger.everythingsearch.plist

# 2. Reload to apply changes
launchctl bootout gui/$(id -u)/com.jigger.everythingsearch
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist

# Verify
launchctl list | grep everythingsearch
```

#### Full Disk Access Authorization (Suppress Permission Dialogs)

**Symptom**: Every time the scheduled indexer runs, macOS shows a dialog: *"python3.11 wants to access data from other apps."* — requiring manual approval each time.

**Cause**: When launchd runs Python as a background process, macOS TCC intercepts any access to protected directories (such as MWeb's `~/Library/...` database files) until the user explicitly grants permission in System Settings.

**Fix: Grant Full Disk Access to Python**

First, find the real Python executable path used by the project:
```bash
readlink -f ./venv/bin/python
# Example output: /opt/homebrew/Cellar/python@3.11/3.11.15/Frameworks/Python.framework/Versions/3.11/bin/python3.11
```

Then grant access in System Settings:

1. Open **System Settings** → **Privacy & Security** → **Full Disk Access**
2. Click the **「＋」** button at the bottom left
3. Press `Cmd+Shift+G` and paste the full path from the command above, then click **Open**
4. Repeat to also add `/bin/bash` (launchd calls bash first to run the wrapper script)
5. Make sure both entries are **toggled on**

Once granted, the scheduled indexer will run silently in the background with no permission prompts.

> **Watch out for Homebrew Python upgrades**: When Homebrew upgrades Python's minor version (e.g. `3.11.15` → `3.11.16`), the versioned install path changes. You will need to remove the old entry and add the new path in Full Disk Access. Run `readlink -f ./venv/bin/python` again to get the updated path.



## 7. Maintenance and Tuning Guide

### Adjust search strictness
- Decrease `SCORE_THRESHOLD` (e.g. `0.35`) -> stricter
- Increase `SCORE_THRESHOLD` (e.g. `0.60`) -> more results

### Add more target directories
Update `TARGET_DIR` then run full rebuild.

### Change embedding model
Set `EMBEDDING_MODEL` to supported DashScope model and rebuild.

### Change schedule time
Edit `Hour` and `Minute` in `com.jigger.everythingsearch.plist`, then reload with `launchctl`.

### Add new file extension support
Update extension sets in `config.py`; add parser branch in `_read_file_worker` if needed.

---

## 8. Fresh Deployment Guide

Suitable for deploying on a clean Mac.

### Prerequisites
- macOS 10.15+
- Homebrew installed
- DashScope API key

### Installation Steps

```bash
brew install python@3.11
mkdir -p ~/Documents/code
cd ~/Documents/code
tar xzf /path/to/EverythingSearch.tar.gz
cd EverythingSearch
python3.11 -m venv venv
./venv/bin/pip install -r requirements.txt

# For runtime-only environments, you can use:
# ./venv/bin/pip install -r requirements/base.txt
nano config.py
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full
./scripts/run_app.sh start
```

Optional launchd wrappers:
```bash
./scripts/install_launchd_wrappers.sh
```

---

## 9. Copyright

Copyright (c) 2026 jiggersong. Licensed under the MIT License.
