# EverythingSearch

[English](README.md) | [中文](README.zh-CN.md)

EverythingSearch is a **local semantic file search engine for macOS**.
It supports natural-language and keyword queries over your local files, code, and notes.

## Quick Start

```bash
git clone https://github.com/jiggersong/everythingsearch.git
cd everythingsearch
./scripts/install.sh
```

## Common Commands

```bash
make index         # incremental indexing
make index-full    # full reindex
make app           # run app in foreground
make app-status    # status of launchd-managed app
make app-restart   # restart launchd-managed app
make app-stop      # stop launchd-managed app
```

## Documentation Matrix

| Suggested Order | Document | Role | Best For | What You Get |
|-----------------|----------|------|----------|--------------|
| 1 | `docs/INSTALL.en.md` | Installation and operations guide | First installation, machine migration, environment setup | prerequisites, API key setup, install workflow, launchd wrapper setup, daily operation commands |
| 2 | `docs/PROJECT_MANUAL.en.md` | Technical reference manual | Developers, maintainers, contributors | architecture diagram, module boundaries, configuration matrix, indexing/search pipeline, tuning and deployment practices |
| 3 | `docs/CHANGELOG.en.md` | Release and compatibility ledger | Upgrades, regression checks, release review | user-visible changes by version, release links, upgrade context |

## Technical Manual Scope

`docs/PROJECT_MANUAL.en.md` is the canonical technical reference and covers:

| Area | Highlights |
|------|------------|
| Core understanding | project goals, core capabilities, architecture overview |
| System design | architecture diagram, technology stack, repository structure |
| Module internals | `app`, `search`, `indexer`, `incremental`, `embedding_cache` responsibilities |
| Runtime behavior | configuration matrix, indexing/search lifecycle, API surface |
| Operations | launchd service model, daily commands, tuning, fresh deployment checklist |

For Chinese docs, switch via the language link at the top of this page.

## License

MIT License.
