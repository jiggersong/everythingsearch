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
| `scripts/upgrade.sh` | Auto version upgrade script (v1.0+ → latest) |
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

## 9. Version Upgrade

If you have an older version (v1.0.0 or later) installed, this section walks you through upgrading to the latest version. The entire process is handled automatically by `scripts/upgrade.sh` on macOS and requires `rsync` — **you don't need to manually deal with index files or data migration**.

### 9.1 Preparation: Download the new version

**Important: Do not extract or copy the new version directly over your old project directory.** Download it to a **completely separate directory** first:

```bash
# Option 1: via git clone (recommended)
git clone https://github.com/jiggersong/everythingsearch.git ~/Downloads/EverythingSearch-new

# Option 2: Download the zip from GitHub Releases and unzip
# Assuming you unzipped to ~/Downloads/EverythingSearch-new
```

> **Why not overwrite directly?** Your old project directory contains runtime files (virtual environment, index data, logs, config) that could conflict or be lost if overwritten. The upgrade script safely syncs the new code over.

### 9.2 Run the Upgrade

Enter the newly downloaded directory and run the upgrade script:

```bash
cd ~/Downloads/EverythingSearch-new
./scripts/upgrade.sh
```

The script looks for your old installation at `~/Documents/code/EverythingSearch` by default. If it's elsewhere, specify the path:

```bash
./scripts/upgrade.sh /path/to/your/old/installation
```

### 9.3 What Happens During Upgrade

The script walks you through these steps interactively, explaining each one:

**① Version Detection** — The script examines your old project's files (directory structure, index format, config) to determine which version you're upgrading from.

**② Deployment Confirmation** — If the old project path differs from the current directory, the script asks "Deploy new version to old installation path and upgrade?" Choose **Y** (the default).

**③ Data Backup** — The following critical files are backed up to `upgrade_backups_timestamp/` inside the project directory:
- `config.py` (your personal configuration)
- `embedding_cache.db` (embedding cache — preserves API cost savings)
- `chroma_db/` (old vector database)

This is a key-file backup, not a full project snapshot. It does not include the virtual environment, logs, sparse index, scan cache, or every `data/*.db` file.

**④ Config Merge** — The script generates a new `config.py` from the latest template and migrates only these selected fields from the old `config.py`: `MY_API_KEY`, `TARGET_DIR`, `ENABLE_MWEB`, `MWEB_LIBRARY_PATH`, and `MWEB_DIR`. Other custom edits, such as `INDEX_ONLY_KEYWORDS`, `HOST`, `PORT`, `NL_INTENT_MODEL`, or `SEARCH_INTERPRET_MODEL`, return to template defaults and should be copied over manually if still needed.

**⑤ Data Cleanup** — Depending on the detected old version, incompatible files are cleaned up:

| Scenario | Old Version | What Gets Cleaned |
|----------|-------------|-------------------|
| **A** | v1.0.x – v1.1.x | Delete old ChromaDB (metadata format incompatible with v2.x), clear scan cache and index state |
| **B** | v1.2.0 – v1.5.2 | Delete old ChromaDB (no FTS5 sparse index), clear scan cache and index state, keep embedding cache |
| **C** | v2.0.0+ | Index format is compatible — only clear scan cache and index state (rebuilt on next incremental run) |

The integrity check stage ensures `data/` exists before the script continues. If scenario C upgrades successfully but vector search behaves abnormally, delete `data/chroma_db/` and run a full rebuild.

**⑥ Dependency and Launchd Update** — Runs `venv/bin/python -m pip install -r requirements/base.txt` (or `.venv/bin/python` if that is the existing virtual environment), then runs `install_launchd_wrappers.sh` to regenerate wrapper scripts and plist files pointing to the current project path. Your existing auto-start and scheduled indexing setup is preserved.

**⑦ Index Rebuild** — For scenarios A/B, you'll be asked "Rebuild index now?" **Recommended: choose Y**. The script uses `caffeinate -i` to prevent sleep and runs the full rebuild in the foreground. Depending on file count, this may take 10 minutes to several hours. Scenario C only needs a quick incremental index verification.

### 9.4 Post-Upgrade Verification

After the full index rebuild completes, verify everything works:

```bash
cd ~/Documents/code/EverythingSearch   # or your project path

# 1. Run incremental index — should complete without errors
./venv/bin/python -m everythingsearch.incremental

# 2. Perform a search — should return results
./venv/bin/python -m everythingsearch search "test" --json

# 3. Ensure the web service is running
./scripts/run_app.sh restart
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser, search for a few files you remember, and confirm results look correct.

### 9.5 Clean Up

Once the upgrade is successful and everything is confirmed working:

- **New download directory** (e.g. `~/Downloads/EverythingSearch-new`): job done — **delete it**
- **Old project directory** (e.g. `~/Documents/code/EverythingSearch`): **now updated to the latest version** — keep using this one
- **Backup directory** (`upgrade_backups_timestamp/` inside the project): delete after confirming everything is fine

### 9.6 FAQ

**Q: I already overwrote my old directory with the new version. What now?**

No worries. Just run `./scripts/upgrade.sh` from the mixed directory. The script detects this as an in-place upgrade, skips the code sync step, and proceeds directly to config merge and data cleanup.

**Q: The upgrade failed. How do I recover?**

The `upgrade_backups_timestamp/` directory contains key files from before the upgrade, not a full project snapshot. Copy the backed-up `config.py` and data directories back as needed, then redeploy with your old version's code and rebuild the index if required.

**Q: I have multiple TARGET_DIRs. Will my config migrate correctly?**

Yes. The script parses your old `config.py` with Python — whether `TARGET_DIR` is a single string or a list of paths, it's extracted and written into the new config correctly.

## Copyright

Copyright (c) 2026 jiggersong, MIT License.
