# EverythingSearch

[English](README.md) | [中文](README.zh-CN.md)

EverythingSearch is a **local semantic file search engine for macOS**, comparable in spirit to **Everything** on Windows: use **natural language or keywords** to search local documents, code, materials, and notes.

## Core Capabilities

- **File search**: Natural language or keyword queries over indexed files, with sub-second responses—addressing the common gap where macOS built-in search often falls short.
- **Hybrid indexing**: Indexes both file content and filenames, so matches can come from inside documents, not only from names.
- **Position weighting**: Hits in filenames and headings rank higher.
- **Caching model**: The first full index scans the disk and may take a while; afterward, incremental updates keep day-to-day indexing fast and lightweight.
- **Privacy and data flow**: Indexes and vector data stay on your machine by default. Indexing sends text chunks to DashScope (or your configured embedding endpoint) to compute embeddings. When an API key is configured and you use the web NL search flow, the current query and compact result summaries may be sent for intent parsing and optional interpretation. Without a key, the browser does not call the NL pipeline—see [`NL_SEARCH_AND_WEB_UI.en.md`](docs/NL_SEARCH_AND_WEB_UI.en.md).
- **Web UI**: Search in the browser with a flow similar to a web search engine, except your files stay local; filter by file time for tighter results.
- **MWeb support**: If you use MWeb for notes and Markdown, enable one setting to integrate and index MWeb content.

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
make app           # run app in the foreground
make app-status    # status of launchd-managed app
make app-restart   # restart launchd-managed app
make app-stop      # stop launchd-managed app
```

## System Permissions & Automation

After installation, complete these three system-level steps so the service can run reliably in the background:

| Feature | Description |
| --- | --- |
| **Auto-start on login** | The search service (Web UI) is started by launchd after you sign in—no manual launch. |
| **Scheduled index updates** | Incremental indexing runs every 30 minutes by default, keeping the index close to disk state. |
| **Full Disk Access** | Grant Python access to protected locations (e.g. some MWeb data paths) to avoid repeated permission prompts. |

> For detailed steps, see [`PROJECT_MANUAL.en.md`](docs/PROJECT_MANUAL.en.md) §6.5 “System Permissions & Automation Setup”.

## Documentation Matrix

| No | Document | Role | Best For | What You Get |
| --- | --- | --- | --- | --- |
| 1 | [`INSTALL.en.md`](docs/INSTALL.en.md) | Installation and operations guide | First install, new machine, environment setup | Prerequisites, API key, install flow, launchd wrappers, day-to-day commands |
| 2 | [`PROJECT_MANUAL.en.md`](docs/PROJECT_MANUAL.en.md) | Technical reference manual | Development, maintenance, customization | Architecture, module boundaries, config matrix, indexing/search flow, tuning and deployment |
| 3 | [`UI_DESIGN_APPLE_GOOGLE.en.md`](docs/UI_DESIGN_APPLE_GOOGLE.en.md) | Web UI design notes | UI upkeep, HIG/Material alignment, accessibility and motion | Design principles and tokens; bilingual pages linked at the top |
| 4 | [`NL_SEARCH_AND_WEB_UI.en.md`](docs/NL_SEARCH_AND_WEB_UI.en.md) | NL search behavior notes | Smart search integration, default fallback, API checks | Intent route, interpretation route, `exact_focus`, rate limits, behavior without a key |

## Technical Reference Manual Scope

[`PROJECT_MANUAL.en.md`](docs/PROJECT_MANUAL.en.md) is the project's core technical reference manual. It covers:

| Area | Highlights |
| --- | --- |
| Foundations | Project goals, core capabilities, overall architecture |
| System design | Architecture diagram, stack, repository layout |
| Module internals | Responsibilities of `app`, `search`, `indexer`, `incremental`, `embedding_cache` |
| Runtime behavior | Configuration matrix, indexing/search lifecycle, HTTP API surface |
| Operations | launchd service model, common commands, tuning, fresh-deployment checklist |

Use the language links at the top of this page to switch to Chinese.

## License

This project is licensed under the [MIT License](LICENSE).
