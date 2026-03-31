# EverythingSearch Project Manual

[English](PROJECT_MANUAL.en.md) | [中文](PROJECT_MANUAL.md)

## 1. Project Overview

EverythingSearch is a **local semantic file search engine** running on macOS.
It allows users to quickly find local documents, code, and knowledge files using natural language or keywords.

### Core Capabilities

- **Semantic search**: understands intent beyond exact keyword matching
- **Hybrid indexing**: indexes both file content and filenames, so media files can still be found by name
- **Optional MWeb integration**: supports indexed MWeb Markdown exports; can be fully disabled with `ENABLE_MWEB=False`
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
┌───────────────────────▼──────────────────────────────┐
│            Flask Backend (everythingsearch.app)       │
│  /api/search · /api/health · /api/cache/clear · ...   │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│            Search Engine (everythingsearch.search)    │
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
│   ├── app.py                # Flask web app
│   ├── search.py             # Search core
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
│   ├── CHANGELOG.en.md
│   ├── UI_DESIGN_APPLE_GOOGLE.en.md   # Web UI design notes (English)
│   └── UI_DESIGN_APPLE_GOOGLE.md      # Web UI design notes (Chinese)
├── Makefile                  # make shortcuts (make help lists targets)
├── requirements.txt
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

All tunable parameters are centralized in this file:

| Key | Default | Description |
|-----|---------|-------------|
| `MY_API_KEY` | `sk-...` or `DASHSCOPE_API_KEY` env var | DashScope API key |
| `TARGET_DIR` | `/path/to/documents` or `["/path1", "/path2"]` | Root directory/directories to index |
| `ENABLE_MWEB` | `False/True` | Enables MWeb source; when disabled, export/scan and source filter entry are skipped |
| `MWEB_DIR` | `/path/to/MWebMarkDown/File` | MWeb export directory |
| `MWEB_EXPORT_SCRIPT` | `.../mweb_export.py` | MWeb export script path |
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

**Timeout on Unix**: uses `SIGALRM` around ~30s per search where supported; this is process-level timing and not ideal for strict per-request guarantees in multi-thread mode.

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

### 4.6 `everythingsearch.app` - Web Service

Flask routes:
- `GET /` - main page
- `GET /api/search?q=...&source=all|file|mweb` - search API (`limit=1..200` optional)
- `GET /api/health` - runtime and DB/cache state summary
- `POST /api/cache/clear` - clear in-memory search cache
- `GET /api/file/read?filepath=...&max_bytes=...` - read indexed file text
- `GET /api/file/download?filepath=...` - download indexed file
- `POST /api/reveal` - reveal file in Finder
- `POST /api/open` - open file with default app

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

---

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
