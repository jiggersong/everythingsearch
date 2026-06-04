# EverythingSearch Installation & Setup Guide

[English](INSTALL.en.md) | [中文](INSTALL.md)

## Overview

This guide explains how to install EverythingSearch on a fresh macOS machine and how to run it in daily use. EverythingSearch indexes local files, optionally indexes MWeb exports, and exposes a browser UI on `http://127.0.0.1:8000`.

## System Requirements

| Item | Requirement |
| --- | --- |
| OS | macOS 10.15 or newer |
| Disk space | At least 500MB |
| Network | Required for install and indexing; browser smart search and interpretation also need DashScope; `GET /api/search` can run without outbound calls once vectors already exist |
| Python | 3.10 or 3.11 |
| External account | DashScope API key |
| Optional software | MWeb, only if you want MWeb source indexing |

## 1. Get an API Key

1. Open [DashScope Console](https://dashscope.console.aliyun.com).
2. Sign in with your Alibaba Cloud account.
3. Create a new API key.
4. Save the generated key for installation, for example `sk-...`.

## 2. Automatic Installation

```bash
cd /path/to/EverythingSearch
./scripts/install.sh
```

The installer can:

1. Check or install Homebrew and Python.
2. Create the virtual environment and install dependencies.
3. Guide you through API key, target directory, and optional MWeb setup.
4. Optionally install launchd services.
5. Optionally start the first full indexing run.

## 3. Manual Installation

### 3.1 Create the Virtual Environment

```bash
cd /path/to/EverythingSearch
python3.11 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

Runtime-only deployment can use:

```bash
./venv/bin/pip install -r requirements/base.txt
```

### 3.2 Configure the API Key and Local Settings

If `config.py` does not exist yet:

```bash
cp etc/config.example.py config.py
```

Set the main local settings in `config.py`:

```python
MY_API_KEY = "sk-your-real-api-key"
TARGET_DIR = "/Users/your-name/Documents/your-folder"

# Optional when ENABLE_MWEB = True
# MWEB_LIBRARY_PATH = "..."
# MWEB_DIR = "..."
```

Configuration notes:

- Runtime settings come from `config.py`; unset values use safe code defaults
- `MY_API_KEY` and `TARGET_DIR` no longer ship with runnable placeholder values
- If `PERSIST_DIRECTORY`, `INDEX_STATE_DB`, `SCAN_CACHE_PATH`, or `EMBEDDING_CACHE_PATH` are not set, they default under the repository `data/` directory

### 3.3 Build the First Index

```bash
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full
```

### 3.4 Start the Search Service

```bash
./scripts/run_app.sh start
./scripts/run_app.sh status
./scripts/run_app.sh restart
./scripts/run_app.sh stop
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

### 3.5 Optional Local Hostname

To use a memorable local hostname such as `everythingsearch.local`, add it to `/etc/hosts`:

```bash
sudo nano /etc/hosts
```

Append:

```text
127.0.0.1   everythingsearch.local
```

Then visit [http://everythingsearch.local:8000](http://everythingsearch.local:8000).

## 4. Configuration Notes

The full configuration matrix lives in [PROJECT_MANUAL.en.md](PROJECT_MANUAL.en.md). The most common options are below.

### Required Settings

| Key | Notes |
| --- | --- |
| `TARGET_DIR` | Root directory or list of roots to index |
| `MY_API_KEY` | Required for indexing embeddings; browser smart search also needs it |

### Common Optional Settings

| Key | Default | Notes |
| --- | --- | --- |
| `ENABLE_MWEB` | `False` | Enable MWeb export and indexing |
| `MWEB_LIBRARY_PATH` | macOS default path | Override only if MWeb is installed in a non-standard location |
| `MWEB_DIR` | `data/mweb_export` | Local export landing zone for MWeb notes |
| `SPARSE_TOP_K` | `120` | Candidate chunk count for SQLite FTS5 sparse retrieval |
| `DENSE_TOP_K` | `120` | Candidate chunk count for vector database dense retrieval |
| `FUSION_TOP_K` | `200` | Candidate chunk count after RRF fusion sorting |
| `RERANK_MODEL` | `qwen3-rerank` | Precise ranking model (depends on DashScope, e.g., `qwen3-rerank`, `gte-rerank`) |
| `CHUNK_SIZE` | `500` | Chunk size for indexing |
| `MAX_CONTENT_LENGTH` | `20000` | Max indexed characters per file |
| `NL_INTENT_MODEL` | `qwen-turbo` | Intent model for `POST /api/search/nl` |
| `SEARCH_INTERPRET_MODEL` | `qwen-turbo` | Interpretation model |
| `RATE_LIMIT_NL_PER_MIN` | `10` | Per-IP limit for NL search |
| `RATE_LIMIT_INTERPRET_PER_MIN` | `10` | Per-IP limit for interpretation routes |
| `TRUST_PROXY` | `False` | Trust `X-Forwarded-For` only behind a controlled reverse proxy |

## 5. launchd and Scheduled Incremental Indexing

The recommended way to install launchd wrappers and plist files is:

```bash
./scripts/install_launchd_wrappers.sh
```

This script (**multi-instance**): each install directory gets a unique 12-hex suffix from `sha256(absolute path)`, so two clones can both register LaunchAgents without overwriting each other.

- writes `scripts/.launchd_instance` and `scripts/.launchd_instance.mk` (for `run_app.sh` and `Makefile`)
- generates `scripts/launchd_app_wrapper.sh` and `scripts/launchd_index_wrapper.sh` under the repo (launchd runs `/bin/bash` on these, then they `cd` into `APP_DIR`)
- writes `~/Library/LaunchAgents/com.jigger.everythingsearch.app.<suffix>.plist` and `com.jigger.everythingsearch.index.<suffix>.plist` (Label matches filename)

Scheduling behavior:

- the app service uses `RunAtLoad + KeepAlive`
- scheduled indexing uses `RunAtLoad + StartInterval`
- the default interval is `1800` seconds, which is about every 30 minutes

Templates under [`scripts/launchd/`](../scripts/launchd/) are **legacy single-instance** samples; prefer plists generated by `install.sh` or this script.

If you still have old fixed-name plists (`com.jigger.everythingsearch.app.plist` / `com.jigger.everythingsearch.plist`), `bootout` and remove them when no longer needed to avoid confusion alongside multi-instance jobs.

macOS TCC note:

- `ProgramArguments` uses `/bin/bash` plus in-repo wrappers; logs stay under each instance’s `APP_DIR/logs`

### ⚠️ Full Disk Access (Required)

After installing launchd services, you **must** grant Full Disk Access to Python and bash. Otherwise, macOS will show a "python3.11 wants to access data from other apps" prompt on every scheduled indexing run, requiring manual approval each time.

**First, find the real Python interpreter path:**

```bash
cd /path/to/EverythingSearch
./venv/bin/python -c 'import sys; print(sys.executable)'
```

**Then grant access in System Settings:**

1. Open **System Settings → Privacy & Security → Full Disk Access**
2. Click the **+** button
3. Press `Cmd+Shift+G`, paste the Python path from above, click **Open**
4. Click **+** again, add `/bin/bash` the same way (launchd invokes bash → wrapper script)
5. Make sure both toggles are **ON**

You can also open the panel directly from the terminal:

```bash
open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
```

> **Note**: Homebrew Python patch upgrades (e.g. `3.11.15` → `3.11.16`) change the path — you'll need to remove the old entry and re-add the new one. Run the `python -c` command above anytime to check the current path.

## 6. Daily Operations

### Make Shortcuts

```bash
make help
make index
make index-full
make search q="your search query"
make start
make status
make restart
make stop
```

`make index` and `make index-full` print file scale, estimated index chunks, estimated tokens, and estimated duration before work starts. During long runs they log progress every 30 seconds and finish with a short summary. Token counts are local estimates; actual billing is determined by the model provider.

### Manual Incremental Index

```bash
./venv/bin/python -m everythingsearch.incremental
```

After incremental indexing completes, the search service is **restarted automatically** to load new data (if launchd is not managing the service and auto-restart fails, follow the log and run `./scripts/run_app.sh start` manually).

Incremental indexing first reports added, modified, and deleted file counts plus estimated cost. If the current vector collection is missing, it explicitly falls back to a full rebuild.

### Full Rebuild

`make index-full` (or `incremental --full`) rebuilds the index from scratch so it matches your current `config.py` and on-disk files.

> **Target behavior from v2.5.0** (docs updated; running processes may still use the v2.4.0 implementation until the code ships): the default is a **true full rebuild**—in addition to sparse / chroma / index_state, it **deletes** `embedding_cache.db` and `scan_cache.db` so stale caches cannot cause search inconsistencies. This may cost more time and Embedding tokens, but the outcome is the most reliable.

**Recommended flow (typical users)**

1. (Optional) disable scheduled incremental to avoid lock contention: `make index-disable`
2. Run a clean rebuild (**by default** auto-suspends and restores the search service; no manual `stop` / `restart`):

```bash
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full
```

A summary of files to be removed or kept is printed before work starts. Token figures are local estimates; billing is per DashScope.

**Embedding rate limits**: Mainland China `text-embedding-v4` **shares** quota with v1–v3 (RPS 30, TPM 1,200,000 input tokens, batch size 10). Defaults such as `EMBED_RATE_RPS_LIMIT=28` sit slightly below official caps. Dense writes retry on 429 with backoff; after repeated failure the process exits 1—resume with `--resume --keep-caches`. See [SEARCH_ACCURACY_TECHNICAL_DESIGN.en.md](SEARCH_ACCURACY_TECHNICAL_DESIGN.en.md) §9.1.

**Advanced flags** (opt in when you want to save time or tokens):

| Flag | Effect |
|------|--------|
| `--keep-embedding-cache` | Keep vector cache; fewer Embedding API calls |
| `--keep-scan-cache` | Keep parse cache; unchanged files skip heavy re-parsing |
| `--keep-caches` | Keep both caches |
| `--resume` | Continue after interruption (**always keeps** both caches and checkpoint; incompatible with a from-scratch wipe) |
| `--dry-run` | Preview touched files only; no deletes or writes |

Examples:

```bash
# Resume after crash (save parse + Embedding cost)
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full --resume --keep-caches

# Keep vectors only; files are still fully re-parsed
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full --keep-embedding-cache
```

**Notes**

- After changing `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `CHUNK_SIZE`, etc., use the **default** full rebuild (no `--keep-*`), unless you understand partial cache invalidation.  
- `--resume` fails if the checkpoint does not match the current config fingerprint; drop `--resume` for a clean rebuild.  
- If Dense embedding retries are exhausted, the process exits 1; checkpoint is kept—resume with `make index-full ARGS="--resume --keep-caches"`.  
- If another index run is already active (including scheduled incremental), a new full rebuild is refused; overlapping incremental runs skip.  
- See [PROJECT_MANUAL.en.md](PROJECT_MANUAL.en.md) §4.4, §4.4.2, and §6 for details.

## 7. FAQ

- **Search cannot find a specific file**: work through these checks — most misses are “not in the index”, not a ranking bug.
  1. **Still on disk**: confirm the path in Finder or the terminal; moved, renamed, or deleted files will not match.
  2. **Under `TARGET_DIR`**: only configured roots (and MWeb export when enabled) are scanned; with multiple installs, verify the Web port maps to the right `config.py`.
  3. **Indexed by this instance**: in the **running instance’s** data directory:
     ```bash
     sqlite3 data/sparse_index.db \
       "SELECT filepath, filename FROM sparse_chunks WHERE filename LIKE '%keyword%' LIMIT 20;"

     sqlite3 index_state.db \
       "SELECT filepath, mtime FROM file_index WHERE filepath LIKE '%keyword%' LIMIT 20;"
     ```
     Zero rows in both → the file was never indexed here; place it under `TARGET_DIR` and run `make index` or incremental indexing.
  4. **Extension and filters**: check supported types; path/date/filename-only filters on the Web UI narrow results.
  5. **Full filename with extension fails on very old indexes**: rebuild with `make index-full` or search without the extension.
  6. **Same file listed twice (v2.3.4 and earlier)**: common with legacy Chroma `file_id`s after upgrading from v1.x; v2.3.5+ dedupes by physical path; a full reindex aligns `file_id`s.
- **`error: externally-managed-environment` during install**: use the project virtualenv pip instead of the system pip.
- **launchd startup keeps failing**: rerun `./scripts/install_launchd_wrappers.sh` and verify the generated wrapper paths.
- **No DashScope key on this machine**: indexing cannot generate vectors, and browser smart search is disabled; the UI falls back to `GET /api/search` only.

## 8. File List

| File or Path | Purpose |
| --- | --- |
| `scripts/install.sh` | Interactive installer |
| `scripts/install_launchd_wrappers.sh` | Generate launchd wrappers and plist files |
| `scripts/run_app.sh` | App lifecycle management |
| `docs/PROJECT_MANUAL.en.md` | Technical manual |
| `docs/NL_SEARCH_AND_WEB_UI.en.md` | NL search behavior notes |
| `etc/config.example.py` | Config template |
| `everythingsearch/app.py` | Flask entry and route registration |
| `everythingsearch/retrieval/` | ★ Core multi-way retrieval pipeline (query_planner / sparse / dense / fusion / reranking / aggregation) |
| `everythingsearch/indexing/` | Dual-write index components (FTS5 sparse + ChromaDB dense) |
| `everythingsearch/services/` | Service layer |
| `everythingsearch/request_validation.py` | Request parsing and validation |
| `everythingsearch/infra/` | Settings, rate limiting, logging-related infrastructure |
| `scripts/launchd/*.plist` | Legacy single-instance launchd templates (reference) |
| `scripts/launchd_app_wrapper.sh` | Generated per install (gitignored) |
| `scripts/launchd_index_wrapper.sh` | Generated per install (gitignored) |

Version history: [GitHub Releases](https://github.com/jiggersong/everythingsearch/releases).

## 9. Updating an existing install

After pulling the latest code, reinstall dependencies if `requirements/base.txt` changed, refresh launchd wrappers when scripts change, and run `make index-full` when index formats change:

```bash
git pull
./venv/bin/pip install -r requirements/base.txt
./scripts/install_launchd_wrappers.sh
make index-full
./scripts/run_app.sh restart
```

Back up `config.py` before updating. Merging code does not auto-migrate custom settings; see `docs/CHANGELOG.md` for breaking changes.

## Copyright

Copyright (c) 2026 jiggersong, MIT License.
