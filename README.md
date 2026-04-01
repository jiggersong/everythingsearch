# EverythingSearch

[English](README.md) | [中文](README.zh-CN.md)

EverythingSearch is a **local semantic file search engine for macOS**.
Equivalent to the capabilities of the 'Everything' software on Windows. It supports natural-language and keyword queries over your local files, code, and notes.

## Core Capabilities

- **Semantic search**: understands intent beyond exact keyword matching
- **Hybrid indexing**: indexes both file content and filenames, so media files can still be found by name
- **Seamless MWeb Integration (Optional)**: Enable built-in MWeb note syncing with a single switch. Fully managed extraction and retrieval labeled in UI; disable entirely with `ENABLE_MWEB=False`
- **Position weighting**: keywords in filename/headings receive higher ranking
- **Embedding cache**: avoids repeated API embedding calls; SQLite uses WAL and connection pooling
- **Incremental indexing**: updates only new/modified/deleted files on each run
- **Search memory cache and health API**: repeated queries can hit memory cache; includes `/api/health` and `POST /api/cache/clear`
- **Robust security boundaries**: enforces strict pre-request validation (HTTP 400 intercepts) and bulletproof path traversal prohibition, ensuring local file operations strictly reside within indexed boundaries
- **Privacy-first with controlled cloud usage**: index and vector DB stay local (ChromaDB); cloud API is used only for embedding generation
- **Web UI**: source filter, sorting, pagination, highlights, Finder reveal

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

## Documentation Matrix

| No  | Document                                                                                                                                    | Role                              | Best For                                                        | What You Get                                                                                                             |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 1   | [`INSTALL.en.md`](docs/INSTALL.en.md)                                                                                                       | Installation and operations guide | First installation, machine migration, environment setup        | prerequisites, API key setup, install workflow, launchd wrapper setup, daily operation commands                          |
| 2   | [`PROJECT_MANUAL.en.md`](docs/PROJECT_MANUAL.en.md)                                                                                         | Technical reference manual        | Developers, maintainers, contributors                           | architecture diagram, module boundaries, configuration matrix, indexing/search pipeline, tuning and deployment practices |
| 3   | [`UI_DESIGN_APPLE_GOOGLE.en.md`](docs/UI_DESIGN_APPLE_GOOGLE.en.md)                                                                           | Web UI design notes               | UI maintenance, HIG/Material alignment, a11y/motion conventions | design principles and tokens; bilingual pages cross-linked at the top                                                  |

## Technical Manual Scope

[`PROJECT_MANUAL.en.md`](docs/PROJECT_MANUAL.en.md) is the canonical technical reference and covers:

| Area               | Highlights                                                                    |
| ------------------ | ----------------------------------------------------------------------------- |
| Core understanding | project goals, core capabilities, architecture overview                       |
| System design      | architecture diagram, technology stack, repository structure                  |
| Module internals   | `app`, `search`, `indexer`, `incremental`, `embedding_cache` responsibilities |
| Runtime behavior   | configuration matrix, indexing/search lifecycle, API surface                  |
| Operations         | launchd service model, daily commands, tuning, fresh deployment checklist     |

For Chinese docs, switch via the language link at the top of this page.

## License

[MIT License](LICENSE).
