# Changelog (English)

## [1.2.3] - 2026-03-26

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

- Daily rotating logs for gunicorn and launchd wrapper logs.
- launchd wrapper and script path alignment updates.

## [1.2.0] - 2026-03-23

- Repository layout reorganization.
- Module entrypoint normalization (`python -m everythingsearch.*`).

## [1.1.0] - 2025-03-23

- Added `/api/health` and `/api/cache/clear`.
- Added tests and caching improvements.
