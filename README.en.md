# EverythingSearch

EverythingSearch is a **local semantic search engine for macOS**.  
It helps you find local documents, code, and notes using natural language queries and keywords.

> Think of it as "Everything + semantic understanding": not only filename matching, but also intent-level retrieval.

## Language

- English (default): `README.en.md` (this file)
- Chinese: `README.zh-CN.md`

## Key Features

- Semantic retrieval over local files
- Hybrid indexing (content + filename)
- Optional MWeb markdown integration
- Incremental indexing (new/modified/deleted files only)
- Local-first storage with ChromaDB
- Browser UI with source filters, sorting, highlighting, and Finder reveal

## Quick Start

```bash
git clone https://github.com/jiggersong/everythingsearch.git
cd everythingsearch
./scripts/install.sh
```

For manual setup and operations:

- Installation guide (EN): `docs/INSTALL.en.md`
- Project manual (EN): `docs/PROJECT_MANUAL.en.md`
- Changelog (EN): `docs/CHANGELOG.en.md`

Chinese docs are also available:

- 安装说明（中文）: `docs/INSTALL.md`
- 项目手册（中文）: `docs/PROJECT_MANUAL.md`
- 变更记录（中文）: `docs/CHANGELOG.md`

## Common Commands

```bash
make index         # incremental indexing
make index-full    # full reindex
make app           # run app in foreground
make app-status    # status of launchd-managed app
make app-restart   # restart launchd-managed app
make app-stop      # stop launchd-managed app
```

## License

MIT License.
