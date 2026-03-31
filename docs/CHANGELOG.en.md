# Changelog

[English](CHANGELOG.en.md) | [中文](CHANGELOG.md)

This file records user-visible changes of EverythingSearch and is intended to stay in sync with GitHub Releases tags.

## [1.3.3] - 2026-03-31

[GitHub Release](https://github.com/jiggersong/everythingsearch/releases/tag/v1.3.3)

### Changed

- **Makefile**: added a **`make help`** target that prints every shortcut target with a one-line description.
- **Docs**: added **`docs/UI_DESIGN_APPLE_GOOGLE.en.md`** (English) with the same structure as the Chinese page and cross-links at the top; aligned the Chinese design token table with implemented CSS variables. Extended the `README` / `README.zh-CN` documentation matrix with a Web UI design row; updated `INSTALL` / `INSTALL.en` and `PROJECT_MANUAL` / `PROJECT_MANUAL.en` to document **`make help`** and to list the root **`Makefile`** plus the bilingual UI design files in the repository tree.

## [1.3.2] - 2026-03-31

[GitHub Release](https://github.com/jiggersong/everythingsearch/releases/tag/v1.3.2)

### Changed

- **Web UI**: refreshed search page styling and interactions in `everythingsearch/templates/index.html`, guided by common **Apple HIG** and **Google Material Design 3** patterns—system font stack, capsule search field with focus ring, sidebar/history hierarchy, result cards and filter chips, pagination and button hit targets, light/dark tokens and elevation; added `prefers-reduced-motion` and `focus-visible` support. **No change** to search behavior or APIs.
- **Docs**: added **`docs/UI_DESIGN_APPLE_GOOGLE.md`** (Chinese) describing the UI approach and acceptance notes.

## [1.3.1] - 2026-03-27

[GitHub Release](https://github.com/jiggersong/everythingsearch/releases/tag/v1.3.1)

### Fixed

- **Dependency (ChromaDB)**: bumped `chromadb` from **1.5.2** to **1.5.5**. On **Python 3.14** with **Pydantic 2.12+** (where `BaseSettings` moved to `pydantic-settings`), older Chroma incorrectly fell back to **`pydantic.v1`**, which raised **`pydantic.v1.errors.ConfigError: unable to infer type for attribute "chroma_server_nofile"`** during import and broke **`everythingsearch/incremental.py`** (and anything that imports `chromadb`). Chroma **1.5.5** uses **`pydantic_settings.BaseSettings`** with Pydantic v2 validators, restoring imports and indexing.

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
