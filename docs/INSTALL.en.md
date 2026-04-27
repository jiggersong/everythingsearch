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

Prefer the API key through an environment variable:

```bash
export DASHSCOPE_API_KEY="sk-your-real-api-key"
```

Then confirm the main local settings in `config.py`:

```python
MY_API_KEY = ""
TARGET_DIR = "/Users/your-name/Documents/your-folder"

# Optional when ENABLE_MWEB = True
# MWEB_LIBRARY_PATH = "..."
# MWEB_DIR = "..."
```

Configuration precedence:

- Environment variables override `config.py`
- `config.py` is still supported as the compatibility layer
- `DASHSCOPE_API_KEY`, `MY_API_KEY`, and `TARGET_DIR` no longer ship with runnable placeholder values
- If `PERSIST_DIRECTORY`, `INDEX_STATE_DB`, `SCAN_CACHE_PATH`, or `EMBEDDING_CACHE_PATH` are not set, they default under the repository `data/` directory

### 3.3 Build the First Index

```bash
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full
```

### 3.4 Start the Search Service

Foreground development mode:

```bash
./venv/bin/python -m everythingsearch.app
# or
./scripts/run_app.sh dev
```

Background service mode:

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
| `DASHSCOPE_API_KEY` or `MY_API_KEY` | Required for indexing embeddings; browser smart search also needs it |

### Common Optional Settings

| Key | Default | Notes |
| --- | --- | --- |
| `ENABLE_MWEB` | `False` | Enable MWeb export and indexing |
| `MWEB_LIBRARY_PATH` | macOS default path | Override only if MWeb is installed in a non-standard location |
| `MWEB_DIR` | `data/mweb_export` | Local export landing zone for MWeb notes |
| `SPARSE_TOP_K` | `120` | Candidate chunk count for SQLite FTS5 sparse retrieval |
| `DENSE_TOP_K` | `120` | Candidate chunk count for vector database dense retrieval |
| `FUSION_TOP_K` | `200` | Candidate chunk count after RRF fusion sorting |
| `RERANK_MODEL` | `gte-rerank` | Precise ranking model (depends on DashScope, e.g., `qwen3-rerank`, `gte-rerank`) |
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

This script:

- generates `~/.local/bin/everythingsearch_start.sh`
- generates `~/.local/bin/everythingsearch_index.sh`
- writes `~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist`
- writes `~/Library/LaunchAgents/com.jigger.everythingsearch.plist`

Scheduling behavior:

- the app service uses `RunAtLoad + KeepAlive`
- scheduled indexing uses `RunAtLoad + StartInterval`
- the default interval is `1800` seconds, which is about every 30 minutes

Reference plist templates live under [`scripts/launchd/`](../scripts/launchd/), but the generated files in `~/Library/LaunchAgents/` are the ones actually used at runtime.

macOS TCC note:

- LaunchAgent processes should not point directly at scripts or log paths under protected locations such as `~/Documents`
- the wrapper scripts under `~/.local/bin/` avoid that restriction and `cd` into the repo internally

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
make app
make app-status
make app-restart
make app-stop
```

### Manual Incremental Index

```bash
./venv/bin/python -m everythingsearch.incremental
./scripts/run_app.sh restart
```

### Full Rebuild

```bash
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full
./scripts/run_app.sh restart
```

## 7. FAQ

- **Search cannot find a file that exists**: verify the extension is supported, the file is under `TARGET_DIR`, then rerun incremental indexing.
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
| `everythingsearch/services/` | Service layer |
| `everythingsearch/request_validation.py` | Request parsing and validation |
| `everythingsearch/infra/` | Settings, rate limiting, logging-related infrastructure |
| `scripts/launchd/*.plist` | Reference launchd templates |
| `~/.local/bin/everythingsearch_start.sh` | Generated app wrapper |
| `~/.local/bin/everythingsearch_index.sh` | Generated incremental-index wrapper |

Version history: [GitHub Releases](https://github.com/jiggersong/everythingsearch/releases).

## Copyright

Copyright (c) 2026 jiggersong, MIT License.
