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
cp etc/config.example.py config.py
```

Edit `config.py`:

- Required: `MY_API_KEY`, `TARGET_DIR`
- Optional: `ENABLE_MWEB`, `MWEB_DIR`, `MWEB_EXPORT_SCRIPT`

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

Main config file: `config.py`

- Core: API key, target directories
- Search tuning: `SEARCH_TOP_K`, `SCORE_THRESHOLD`
- Index tuning: `CHUNK_SIZE`, `MAX_CONTENT_LENGTH`
- Data source: `ENABLE_MWEB`

## 5. Scheduled Incremental Indexing

Use launchd wrappers:

```bash
./scripts/install_launchd_wrappers.sh
```

This installs:

- app service: `com.jigger.everythingsearch.app`
- scheduled indexing: `com.jigger.everythingsearch`

## 6. Daily Operations

```bash
make index
make index-full
make app
make app-status
make app-restart
make app-stop
```

Equivalent commands are available through `./scripts/run_app.sh` and Python module entrypoints.

## 7. FAQ / Common Issues

- **Index changes not reflected in search**: restart app (`make app-restart`)
- **Long full rebuild interrupted by sleep**: run with `caffeinate -i`
- **launchd startup issues**: regenerate wrappers with `./scripts/install_launchd_wrappers.sh`

## 8. File List (Key Components)

- `scripts/install.sh`: installer
- `scripts/run_app.sh`: app lifecycle management
- `scripts/install_launchd_wrappers.sh`: launchd wrapper setup
- `docs/PROJECT_MANUAL.en.md`: technical manual
- `docs/CHANGELOG.en.md`: release notes

## Copyright

Copyright (c) 2026 jiggersong, MIT License.
