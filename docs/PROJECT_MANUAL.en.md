# EverythingSearch Project Manual (English)

## Overview

EverythingSearch is a local semantic search system for macOS.

Main capabilities:

- Semantic + keyword search
- Hybrid indexing (filename/content)
- Incremental index updates
- Optional MWeb source
- Local ChromaDB vector storage

## Architecture

- `everythingsearch.app`: Flask API and UI server
- `everythingsearch.search`: query pipeline and ranking
- `everythingsearch.indexer`: full indexing
- `everythingsearch.incremental`: incremental updates
- `everythingsearch.embedding_cache`: embedding cache over SQLite

## Run Modes

```bash
./venv/bin/python -m everythingsearch.app
./scripts/run_app.sh start|stop|restart|status|dev
```

## Indexing

```bash
python -m everythingsearch.incremental
python -m everythingsearch.incremental --full
./venv/bin/python everythingsearch/incremental.py
```

## Makefile Shortcuts

```bash
make index
make index-full
make app
make app-status
make app-restart
make app-stop
```

## API Endpoints

- `GET /api/search`
- `GET /api/health`
- `POST /api/cache/clear`
- `GET /api/file/read`
- `GET /api/file/download`
- `POST /api/reveal`
- `POST /api/open`

## Chinese Version

See `docs/PROJECT_MANUAL.md`.
