# EverythingSearch Installation & Setup Guide

[English](INSTALL.en.md) | [中文](INSTALL.md)

## Overview

This document explains how to install EverythingSearch on a fresh macOS machine and how to operate it in daily use.

## System Requirements

| Item | Requirement |
|------|-------------|
| OS | macOS 10.15 or newer |
| Disk space | At least 500MB |
| Network | Required during installation/indexing; search itself is local |
| Python | 3.10 or 3.11 |
| External account | DashScope API key |
| Optional software | MWeb (only if you need MWeb source indexing) |

## 1. Get API Key (Before Installation)

1. Open [DashScope Console](https://dashscope.console.aliyun.com)
2. Sign in and create an API key
3. Save the key for installation (`sk-...`)

## 2. Automatic Installation (Recommended)

```bash
cd /path/to/EverythingSearch
./scripts/install.sh
```

The installer helps you configure API key, index directory, optional MWeb integration, launchd setup, and first full indexing.

## 3. Manual Installation

```bash
python3.11 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# For runtime-only installation, you can use:
# ./venv/bin/pip install -r requirements/base.txt
cp etc/config.example.py config.py
```

Prefer setting the API key via environment variable first:

```bash
export DASHSCOPE_API_KEY="sk-your-real-api-key"
```

Then edit `config.py`:

- Required: `TARGET_DIR`
- Recommended: keep `MY_API_KEY = ""` and let `DASHSCOPE_API_KEY` supply the key
- Optional: `ENABLE_MWEB`, `MWEB_LIBRARY_PATH`

Config precedence:

- Environment variables override `config.py`
- `config.py` is still supported during the migration window
- `DASHSCOPE_API_KEY`, `MY_API_KEY`, and `TARGET_DIR` no longer ship with runnable placeholder defaults
- If `PERSIST_DIRECTORY`, `INDEX_STATE_DB`, `SCAN_CACHE_PATH`, or `EMBEDDING_CACHE_PATH` are not set explicitly, they default under the current repository's `data/` directory; for packaged or non-repo deployments, set them explicitly

Build first index:

```bash
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full
```

Start app:

```bash
./scripts/run_app.sh start
./scripts/run_app.sh status
```

Foreground mode:

```bash
./venv/bin/python -m everythingsearch.app
```

## 4. Configuration

Main local config file: `config.py`

Runtime load order:

- environment variables
- repository-root `config.py`
- safe in-code defaults for non-sensitive options only

- Core: API key, target directories
- Search tuning: `SEARCH_TOP_K`, `SCORE_THRESHOLD`
- Index tuning: `CHUNK_SIZE`, `MAX_CONTENT_LENGTH`
- Data source: `ENABLE_MWEB`

For non-repo or packaged deployments, explicitly configure `PERSIST_DIRECTORY`, `INDEX_STATE_DB`, `SCAN_CACHE_PATH`, and `EMBEDDING_CACHE_PATH` instead of relying on inferred defaults.

## 5. Scheduled Incremental Indexing

Use launchd wrappers:

```bash
./scripts/install_launchd_wrappers.sh
```

This installs:

- app service: `com.jigger.everythingsearch.app`
- scheduled indexing: `com.jigger.everythingsearch`

## 6. Daily Operations

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

When you are unsure which targets exist, run **`make help`** (kept in sync with the root `Makefile`).

Equivalent commands are available through `./scripts/run_app.sh` and Python module entrypoints.

## 7. FAQ / Common Issues

- **Occasional 400 Bad Request from API?**: This strictly means the request payload/parameters were invalid (e.g., malformed JSON, missing filepath, or unauthorized path traversal beyond the indexed boundary). Check your client or script inputs.
- **Index changes not reflected in search**: restart app (`make app-restart`)
- **Long full rebuild interrupted by sleep**: run with `caffeinate -i`
- **launchd startup issues**: regenerate wrappers with `./scripts/install_launchd_wrappers.sh`

## 8. File List (Key Components)

- `scripts/install.sh`: installer
- `scripts/run_app.sh`: app lifecycle management
- `scripts/install_launchd_wrappers.sh`: launchd wrapper setup
- `docs/PROJECT_MANUAL.en.md`: technical manual
- `everythingsearch/app.py`: Flask routing entry and application bus
- `everythingsearch/services/`: Core service logic decoupling
- `everythingsearch/request_validation.py`: HTTP JSON validation intercepting bad requests
- `everythingsearch/infra/`: Infrastructure (settings, logging)

Version history: [GitHub Releases](https://github.com/jiggersong/everythingsearch/releases).

## Copyright

Copyright (c) 2026 jiggersong, MIT License.
