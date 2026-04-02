# EverythingSearch

[English](README.md) | [中文](README.zh-CN.md)

EverythingSearch is a **local semantic file search engine for macOS**. It offers capabilities comparable to the Everything utility on Windows: use natural language or keywords to search local documents, code, materials, and notes.

## Core Capabilities

- **File search**: Fuzzy keyword search across all indexed files with sub-second results—addressing the common pain that macOS built-in search is often ineffective
- **Hybrid indexing**: Indexes both file content and filenames, so you can find information that lives inside files, not just in names
- **Position weighting**: Matches in filenames and headings rank higher
- **Caching model**: The first full index after install can take a while while the disk is scanned; afterward, incremental updates keep the index fast
- **Privacy**: All data and operations stay on your machine; a cloud API is used only when generating embeddings, so you need not worry about data security for local search and storage
- **Web UI**: Search in the browser the way you use Google to find information on the web—except your files are local, with a simple, friendly flow. Filter by file time for more precise results
- **MWeb support**: If you are already using MWeb for your notes and as a Markdown editor, flip one switch to take over integration and index your MWeb content in one step

---

## Quick Start

```bash
git clone https://github.com/jiggersong/everythingsearch.git
cd everythingsearch
./scripts/install.sh
```

## Common Commands

```bash
make help          # list all make targets with short descriptions
make index         # incremental indexing
make index-full    # full reindex
make app           # run app in foreground
make app-status    # status of launchd-managed app
make app-restart   # restart launchd-managed app
make app-stop      # stop launchd-managed app
```

## System Permissions & Automation

After installation, complete these three system-level configurations for stable, hands-free background operation:

| Feature | Description |
|---------|-------------|
| **Auto-start on login** | The search service (Web UI) is launched automatically by launchd after you log in—no manual steps |
| **Scheduled index updates** | Incremental indexing runs every 30 minutes so search stays up to date |
| **Full Disk Access** | Grant Python access to protected locations (e.g. MWeb data) so you are not prompted on every run |

> For detailed setup steps, see [`PROJECT_MANUAL.en.md`](docs/PROJECT_MANUAL.en.md) §6.5 “System Permissions & Automation Setup”.

## Documentation Matrix

| No | Document | Role | Best For | What You Get |
| --- | --- | --- | --- | --- |
| 1 | [`INSTALL.en.md`](docs/INSTALL.en.md) | Installation and operations guide | First install, new machine migration, environment setup | Prerequisites, API key setup, install flow, launchd wrapper scripts, day-to-day commands |
| 2 | [`PROJECT_MANUAL.en.md`](docs/PROJECT_MANUAL.en.md) | Technical reference manual | Development, maintenance, customization or extension | Architecture, module boundaries, configuration matrix, indexing/search flow, tuning and deployment |
| 3 | [`UI_DESIGN_APPLE_GOOGLE.en.md`](docs/UI_DESIGN_APPLE_GOOGLE.en.md) | Web UI design notes | UI upkeep, HIG/Material alignment, accessibility and motion | Design principles and tokens; bilingual pages linked at the top |

## Technical Manual Scope

[`PROJECT_MANUAL.en.md`](docs/PROJECT_MANUAL.en.md) is the core technical manual for this project. It covers:

| Area | Highlights |
| ---- | ---------- |
| Foundations | Project goals, core capabilities, overall architecture |
| System design | Architecture diagram, stack, repository layout |
| Module internals | Responsibilities of `app`, `search`, `indexer`, `incremental`, `embedding_cache` |
| Runtime behavior | Configuration matrix, indexing/search lifecycle, API surface |
| Operations | launchd service model, common commands, tuning, fresh-deployment checklist |

Switch to Chinese via the language link at the top of this page.

## License

This project is licensed under the [MIT License](LICENSE).
