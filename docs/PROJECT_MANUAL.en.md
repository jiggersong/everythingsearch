# EverythingSearch Project Manual

[English](PROJECT_MANUAL.en.md) | [中文](PROJECT_MANUAL.md)

## 1. Project Overview

EverythingSearch is a **local semantic file search engine** running on macOS.
It lets users find local documents, code, and materials quickly using natural language or keywords.

### Core Capabilities

- **File search**: Fuzzy keyword search across all files with sub-second results—addressing the common pain that macOS built-in search is often ineffective
- **Hybrid indexing**: Indexes both file content and filenames, so you can find information that lives inside files, not just in names
- **Position weighting**: Matches in filenames and headings rank higher
- **Caching model**: The first full index after install can take a while while the disk is scanned; afterward, incremental updates keep the index fast
- **Privacy**: Indexed data is stored locally. DashScope is used for embeddings during indexing, and when browser smart search is enabled it also receives the current query text and compact result summaries for intent parsing / interpretation
- **Web UI**: Search in the browser the way you use Google to find information on the web—except your files are local, with a simple, friendly flow. Filter by file time for more precise results
- **MWeb support**: If you are already using MWeb for your notes and as a Markdown editor, flip one switch to take over integration and index your MWeb content in one step

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

| Component | Choice | Description |
|-----------|--------|-------------|
| Language | Python 3.11 | Recommended 3.11 (or 3.10); install dependencies in a virtual environment |
| Orchestration | LangChain | Document load, chunking, and vectorization pipeline |
| Embedding model | Aliyun DashScope text-embedding-v2 | Strong Chinese understanding, low cost |
| Vector database | ChromaDB | Local file-based database; no Docker required |
| Web framework | Flask + Gunicorn | Dev / production HTTP service |
| File parsing | pypdf / python-docx / openpyxl / python-pptx | Extract content from PDF, Word, Excel, PPT |
| Frontend | Single-file HTML + CSS + JS | No Node.js build step |

---

## 3. File Structure

```text
EverythingSearch/
├── config.py                 # Local config (copy from etc/config.example.py; do not commit secrets)
├── etc/
│   └── config.example.py     # Config template
├── everythingsearch/         # Python application package
│   ├── app.py                # Flask entry and app assembly
│   ├── services/             # Business service layer (decoupled core logic)
│   │   ├── file_service.py   # File lifecycle control
│   │   ├── search_service.py # Search cache, concurrency, scheduling
│   │   ├── health_service.py # Liveness checks and warmup scheduling
│   │   ├── nl_search_service.py
│   │   └── search_interpret_service.py
│   ├── request_validation.py # Input validation protocol (unified HTTP 400 contract)
│   ├── file_access.py        # Strict file access boundary; anti path traversal
│   ├── infra/                # Infrastructure layer
│   │   ├── settings.py       # Strongly typed config extraction / accessors
│   │   └── rate_limiting.py
│   ├── search.py             # Core search algorithms
│   ├── indexer.py            # Full index build
│   ├── incremental.py        # Incremental indexing
│   ├── embedding_cache.py    # Embedding cache layer
│   ├── templates/
│   │   └── index.html
│   └── static/
│       └── icon.png
├── data/                     # Local data and cache (default paths; do not commit)
│   ├── chroma_db/            # ChromaDB
│   ├── embedding_cache.db
│   ├── scan_cache.db
│   └── index_state.db
├── logs/                     # Runtime and scheduled job logs
├── scripts/
│   ├── install.sh
│   ├── run_app.sh            # Search service control (start/stop/restart/dev)
│   ├── run_tests.sh
│   └── launchd/              # Reference launchd plist copies
├── docs/
│   ├── INSTALL.md
│   ├── PROJECT_MANUAL.md
│   ├── NL_SEARCH_AND_WEB_UI.md
│   ├── NL_SEARCH_AND_WEB_UI.en.md
│   ├── UI_DESIGN_APPLE_GOOGLE.md      # Web UI design notes (Chinese)
│   └── UI_DESIGN_APPLE_GOOGLE.en.md   # Web UI design notes (English)
├── Makefile                  # make shortcuts (`make help` lists targets)
├── requirements.txt
├── requirements/
│   ├── base.txt
│   └── dev.txt
├── pytest.ini
├── tests/
└── venv/

~/.local/bin/
├── everythingsearch_start.sh  # App launchd wrapper (created at install)
└── everythingsearch_index.sh  # Incremental index launchd wrapper (created at install)
```

---

## 4. Core Module Details

### 4.1 `config.py` — Configuration hub

Local settings are concentrated here. Load order: environment variables > repository-root `config.py` > safe in-code defaults.

| Key | Default | Description |
|-----|---------|-------------|
| `MY_API_KEY` | empty string or `DASHSCOPE_API_KEY` env var | Legacy-compatible Alibaba Tongyi DashScope API key field; prefer environment variables |
| `TARGET_DIR` | `/path/to/documents` or `["/path1", "/path2"]` | Root directory or list of roots to index; `TARGET_DIR` env var wins |
| `ENABLE_MWEB` | `False` / `True` | One-switch seamless built-in MWeb note integration; when on, the system takes over automatic export |
| `MWEB_LIBRARY_PATH` | Default macOS library path | MWeb main database directory (optional override) |
| `MWEB_DIR` | `data/mweb_export` | Managed export landing zone for MWeb notes |
| `INDEX_STATE_DB` | `./index_state.db` | Incremental indexing state database |
| `SCAN_CACHE_PATH` | `./scan_cache.db` | Scan/parse cache (skip unchanged files) |
| `EMBEDDING_MODEL` | `text-embedding-v2` | Embedding model name |
| `CHUNK_SIZE` | `500` | Text chunk size (characters) |
| `CHUNK_OVERLAP` | `80` | Chunk overlap (characters) |
| `MAX_CONTENT_LENGTH` | `20000` | Max characters indexed per file |
| `SEARCH_TOP_K` | `250` | Vector retrieval candidate chunks (higher = more recall, slower) |
| `SCORE_THRESHOLD` | `0.35` | Cosine distance threshold (smaller = stricter; matches `settings.py` default) |
| `POSITION_WEIGHTS` | `filename:0.6, heading:0.8, content:1.0` | Position weighting factors |
| `KEYWORD_FREQ_BONUS` | `0.03` | Keyword frequency bonus coefficient |
| `TRUST_PROXY` | `False` | Trust `X-Forwarded-For` from a reverse proxy (for per-IP rate limiting) |
| `NL_INTENT_MODEL` | `qwen-turbo` | NL intent model (prefer JSON Mode–capable models) |
| `SEARCH_INTERPRET_MODEL` | `qwen-turbo` | Model for optional “smart interpretation” of hit lists |
| `NL_TIMEOUT_SEC` | `10` | Intent call timeout (seconds) |
| `INTERPRET_TIMEOUT_SEC` | `20` | Interpretation call timeout (seconds) |
| `NL_MAX_MESSAGE_CHARS` | `1000` | Max characters per intent request |
| `INTERPRET_MAX_RESULTS` | `10` | Max hits summarized in interpretation |
| `RATE_LIMIT_NL_PER_MIN` | `10` | Per-IP requests/minute for `POST /api/search/nl` |
| `RATE_LIMIT_INTERPRET_PER_MIN` | `10` | Per-IP requests/minute for interpretation endpoints |

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

### 4.3 `search.py` — Search engine

**In-memory cache**: Caches results keyed by `(query, source_filter, date_field, date_from, date_to, exact_focus)` (`exact_focus` separates keyword-first mode from the default hybrid pipeline). TTL and max size come from `CACHE_TTL_SECONDS` and `MAX_CACHE_SIZE` in code. After a reindex or when you need immediate consistency, call `POST /api/cache/clear`. Clearing the in-process vector DB cache also clears this cache.

**Timeout control**: Search runs under a shared in-process future-based timeout (`SEARCH_TIMEOUT_SECONDS = 30` by default). Timeouts are **not** turned into empty results; they surface as observable errors (`/api/search` returns HTTP 504). Timed-out searches are not cached. `SEARCH_TIMEOUT_SECONDS = 0` disables timeout enforcement but keeps single-flight and busy protection. Note: after a future times out, the worker thread may still run to completion—known trade-off; until it finishes, new requests may get HTTP 503 (“busy”) to avoid unbounded queue growth.

Search pipeline:

1. **Vector search**: Similarity search in one collection; `source=all|file|mweb` (if `ENABLE_MWEB=False`, only file-sourced results are returned)
2. **Position weighting**: Multiply scores by `chunk_type` weights; filename matches get ~40% boost
3. **Keyword frequency bonus**: Extra score when query terms repeat in a chunk
4. **Per-file dedup**: Keep the best chunk per file
5. **Keyword exact fallback**: ChromaDB `$contains` for documents containing the literal text (multi-term OR)
6. **Merge and sort**: Combine exact and semantic hits, sort by score

**`exact_focus` path** (when `POST /api/search/nl` resolves `match_mode=exact_focus` and sets `SearchRequest.exact_focus=True`):

1. Run the same keyword `$contains` path as step 5, dedupe per file, sort;
2. If there are **no hits**, or every row is **filtered out** by `source` / time `where` clauses, **fall back** to the full vector + keyword hybrid pipeline above so users do not get a false empty result.

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

`app.py` is slim: routes delegate to `services/`, and `request_validation.py` maps bad JSON and invalid parameters to HTTP `400 Bad Request` instead of letting junk hit core code and produce 500s. `file_access.py` enforces that reads, downloads, and open/reveal paths stay inside indexed roots (no traversal).

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
