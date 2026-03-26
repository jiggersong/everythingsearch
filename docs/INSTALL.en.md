# EverythingSearch Installation Guide (English)

This guide explains how to install and run EverythingSearch on macOS.

## Requirements

- macOS 10.15+
- Python 3.10 or 3.11
- DashScope API key

## Recommended Installation

```bash
cd /path/to/EverythingSearch
./scripts/install.sh
```

## Manual Setup

```bash
python3.11 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
cp etc/config.example.py config.py
```

Update `config.py`:

- `MY_API_KEY`
- `TARGET_DIR`
- Optional: MWeb settings

## First Full Index

```bash
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full
```

## Start the App

```bash
./scripts/run_app.sh start
./scripts/run_app.sh status
```

Or foreground mode:

```bash
./venv/bin/python -m everythingsearch.app
```

## Daily Operations

```bash
make index
make index-full
make app
make app-status
make app-restart
make app-stop
```

## Notes

- Index updates require app restart to load fresh vector state.
- launchd wrappers can be (re)generated via `./scripts/install_launchd_wrappers.sh`.
- Chinese install guide remains available at `docs/INSTALL.md`.
