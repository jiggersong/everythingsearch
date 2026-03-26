# Changelog

[English](CHANGELOG.en.md) | [中文](CHANGELOG.md)

This file records user-visible changes of EverythingSearch and is intended to stay in sync with GitHub Releases tags.

## [1.3.0] - 2026-03-26

[GitHub Release](https://github.com/jiggersong/everythingsearch/releases/tag/v1.3.0)

### Changes

- **Documentation internationalization alignment**: completed bilingual (English/Chinese) coverage across `README`, `INSTALL`, `PROJECT_MANUAL`, and `CHANGELOG`, with language switch links at the top of each doc.
- **Technical manual parity**: rewrote `docs/PROJECT_MANUAL.en.md` to match the Chinese manual structure, including numbered sections, architecture diagram, tech/config tables, module deep-dive, operations, and deployment guidance.
- **README documentation portal refresh**: replaced rough guide text with a structured documentation matrix and technical manual scope table; removed duplicated guide sections.
- **Entry-point cleanup**: removed redundant `README.en.md`; `README.md` is now the single English default entry, while `README.zh-CN.md` remains the Chinese entry.

## [1.2.3] - 2026-03-26

[GitHub Release](https://github.com/jiggersong/everythingsearch/releases/tag/v1.2.3)

### Combined updates from 1.2.2 + 1.2.3

- Fixed incremental indexing import behavior so script-path execution works:
  - `./venv/bin/python everythingsearch/incremental.py`
  - Avoids `ImportError: attempted relative import with no known parent package`
- Added `Makefile` shortcuts:
  - `make index`, `make index-full`
  - `make app`, `make app-status`, `make app-restart`, `make app-stop`
- Added English documentation set and kept Chinese docs as selectable alternatives:
  - `README.md` (English entry)
  - `README.zh-CN.md`
  - `docs/INSTALL.en.md`
  - `docs/PROJECT_MANUAL.en.md`
  - `docs/CHANGELOG.en.md`

## [1.2.1] - 2026-03-23

[GitHub Release](https://github.com/jiggersong/everythingsearch/releases/tag/v1.2.1)

- Daily rotating logs for gunicorn and launchd wrapper logs.
- launchd wrapper and script path alignment updates.

## [1.2.0] - 2026-03-23

[GitHub Release](https://github.com/jiggersong/everythingsearch/releases/tag/v1.2.0)

- Repository layout reorganization.
- Module entrypoint normalization (`python -m everythingsearch.*`).

## [1.1.0] - 2025-03-23

[GitHub Release](https://github.com/jiggersong/everythingsearch/releases/tag/v1.1.0)

- Added `/api/health` and `/api/cache/clear`.
- Added tests and caching improvements.

## [1.0.0] - Earlier

Initial public release with semantic search, incremental indexing, Web UI, and local ChromaDB-based indexing/search flow.
