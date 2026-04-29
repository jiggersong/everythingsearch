# Changelog

[English](CHANGELOG.en.md) | [中文](CHANGELOG.md)

## [2.2.2] - 2026-04-29

### Fixes & improvements

- **Index progress and cost hints**: Full rebuilds and incremental updates now print file scale, estimated chunks, estimated tokens, and estimated duration before work starts; long runs log key progress every 30 seconds and end with a short summary.

## [2.2.1] - 2026-04-28

### Fixes & improvements

- **Search pipeline**: Fix inverted relevance percentage; apply `SCORE_THRESHOLD` after aggregation only when rerank scores exist (skip on RRF-only fallback); implement `AGG_EXACT_BONUS` for query-in-content (query length ≥ 2); add aggregation tests.
- **Health**: Vector DB document count now reads Chroma `local_files` collection count.

## [2.2.0] - 2026-04-27

The project keeps shipping updates across releases. To help users on older installs upgrade smoothly to the latest version, I've added an automated upgrade script so you can one-click upgrade your local project to the newest bits and pick up the latest features without a painful manual merge.

### 🚀 One-Click Upgrade

- **`scripts/upgrade.sh`** (macOS): Defaults to probing `~/Documents/code/EverythingSearch`, and accepts an explicit path to your old install. It classifies the upgrade scenario from on-disk layout (legacy Chroma layout, whether the FTS5 sparse index already exists, and so on), `rsync`s new code into the old tree while preserving `config.py` and `data/` until backup and merge are done, snapshots critical files under `upgrade_backups_<timestamp>/`, regenerates `config.py` from the new `etc/config.example.py` with parsed values for `MY_API_KEY`, `TARGET_DIR`, and MWeb-related fields, then cleans incompatible vector stores or only scan caches depending on the scenario, reinstalls dependencies from `requirements/base.txt`, refreshes launchd wrappers, and optionally guides you through a foreground full reindex with `caffeinate` to prevent sleep.

### 📘 Documentation

- **`INSTALL` / `INSTALL.en`**: Adds a full "Version upgrade" section (prep work, command examples, step-by-step walkthrough, post-upgrade checks, and FAQs) and lists `upgrade.sh` in the file manifest.
- **`README` / `README.zh-CN`**: Adds a short version-upgrade section with a pointer to the install guide for the full walkthrough.
- **`PROJECT_MANUAL` / `PROJECT_MANUAL.en`**: Supplements the manual with upgrade steps aligned to the script, so readers who already went through the technical manual can line up their actions with the same path.

## [2.1.2] - 2026-04-27

Many macOS users can get confused by prompts like "Python wants to access data from other apps": this is not a broken build. When background jobs do not have Full Disk Access, macOS blocks each scheduled indexing run with a permission gate. This patch writes the guidance into the install docs and prints the exact paths and steps directly in the installer flow, so users are much less likely to get stuck. No functional search code changed; this is purely a documentation and installation UX hardening pass.

### 📘 Documentation & Install Guidance

- **Install docs**: Added a required **Full Disk Access** section to `INSTALL` - how to print the real Python path from the current venv, why `/bin/bash` must also be added, how to jump straight to the privacy panel from Terminal, and why Homebrew micro-version upgrades may require re-authorization due to path changes.
- **`scripts/install.sh`**: If launchd background services are selected during installation, the script now prints a prominent step-by-step guide at the end, prompts to open the Full Disk Access settings page, and echoes the current interpreter path so users do not have to guess.
- **`scripts/install_launchd_wrappers.sh`**: Adds a short reminder at the end that points users to `INSTALL` and System Settings, so users running only the wrapper installation still see the guidance.

## [2.1.1] - 2026-04-27

After releasing the new architecture a few days ago, I still encountered a few bugs during my own use. This minor release focuses on fortifying the robustness of the underlying retrieval Pipeline, while patching a few deeply hidden edge-case bugs. The overall experience is much "smoother" now, so I highly recommend everyone grab this quick update.

### 🚀 Core Optimizations

- **True Anti-Hang Single-Path Timeout (BUG-004)**: Previously, the `with ThreadPoolExecutor` context block looked elegant, but if an LLM or retrieval API completely hung due to network issues, the main thread would still get dragged into a blocking wait upon exiting the `with` block. This time, I abandoned the implicit context manager in favor of direct lifecycle control (`shutdown(wait=False)` + force cancelling pending tasks). It truly returns immediately when the time is up, so you'll never have to worry about a single anomalous path dragging down the entire query again.
- **Structural Semantic Chunking for Markdown (BUG-007)**: When processing `.md` files or exported MWeb notes before, mechanically chopping text by length caused chunks to indiscriminately inherit *all* headings in the document. I've now brought in LangChain's `MarkdownHeaderTextSplitter`. Text chunks now accurately carry their own specific H1-H6 heading hierarchy, bumping the contextual understanding during vector searches up a solid tier.

### 🐞 Regression Fixes

- **Fixed missing SQLite transactions**: During the dual-writer architecture rewrite, I missed wrapping the `cursor.executemany` operations inside a transaction block, causing bulk operations to miss out on native atomicity and performance optimizations. These are now strictly wrapped within the `with conn:` context.
- **Fixed broken "filler word" stripping in intent recognition**: To prevent injection risks, I previously slapped on a full `html.escape` a bit too hastily. This ended up escaping characters needed for Regex matching, breaking the intelligent search's ability to strip out conversational filler words (like "please find me..."). It's now been dialed back to only filter `<` and `>`, keeping things safe without damaging the business logic.
- **Fixed ghost entries in incremental indexing**: Previously, when the incremental scanner detected a modified file, the old SQLite FTS records weren't being cleaned up, causing duplicate ghost snippets in search results. I've now made sure that updating a file thoroughly uproots the old entries first.

## [2.1.0] - 2026-04-25

I've been playing around with LLM agents like OpenClaw lately, and I realized that letting them directly search my local files would be incredibly powerful! So in this release, I added a command-line interface to the main program, turning it into a robust local file search plugin for agents.

### 🚀 New Features

- **A Super Brain for Agents (CLI)**: You can now use the `python -m everythingsearch search "query" --json` command to get clean, machine-readable JSON search results straight to the terminal.
- **Out-of-the-box OpenClaw Integration Guide**: To make it easy for beginners, I wrote a tutorial on exactly how to configure the "System Prompt" for OpenClaw. Just copy and paste, and your agent instantly gains "local eyes"!
- **Backward-compatible Command Dispatching**: Refactored the command entry point in `__main__.py`. It has zero impact on your existing `make app` commands or background services, so you can upgrade safely.

## [2.0.0] - 2026-04-25

This is the biggest evolution since EverythingSearch was born. During my own heavy daily use, I found that relying purely on vector search wasn't precise enough when looking for specific filenames, and the old UI wasn't quite smooth enough. So, I decided to completely rewrite the underlying search architecture and the frontend UI. For those who want to fork and hack on it, the codebase structure is much more comfortable to work with now.

### 🚀 Experience Upgrades

- **Brand New Conversational UI**: I rebuilt the Web UI to have a conversational style similar to DeepSeek. The search box now supports multi-line input and features a handy toolbar at the bottom. You can easily toggle "AI Mode" on and off, making the whole search and reading experience much more modern and immersive.
- **Transformed Search Accuracy**: I used to run into issues where search results weren't ranked correctly. This time, I introduced a mature architecture: "Multi-way Retrieval + RRF Fusion + LLM Reranking". Combined with the new SQLite FTS5 sparse index, the hit rate and ranking quality have improved drastically, whether you're searching for exact filenames or fuzzy document content.

### 🛠 Architecture & Tech Evolution

- **Complete Retrieval Core Refactor**: I deleted the bloated monolithic file and split the core search logic into a standard retrieval pipeline (`retrieval.pipeline`). It now includes query planning, multi-way retrieval, score fusion, file-level aggregation, and full integration with Rerank models. It's highly extensible and fun to play with.
- **Code Cleanup & Tech Debt Reduction**: I cleaned up leftover test scripts and redundant logs from the early days. I further isolated `app.py`'s routing duties and request interception boundaries, and fixed dependency issues broken during the refactor. The project structure is incredibly clear now, perfect for anyone looking to fork and mod it.

## [1.5.2] - 2026-04-23

This release mainly fixes a minor annoyance I encountered myself: "The file is indexed, so why can't I find it on the page yet?"

### 🐞 Bug Fixes

- **Cache invalidates properly now**: Previously, the search result cache didn't refresh when the index updated. Now, whenever index data changes (whether via a manual `make index` or the scheduled background job), the search cache immediately invalidates. You'll instantly see your latest files.
- **Exact mode behaves better**: Fixed a bug where the backend wasn't correctly receiving and processing "Exact Mode" requests from the Web UI. Now, a normal search initiated by hitting Enter will reliably prioritize literal matches in filenames and paths.

## [1.5.1] - 2026-04-13

To make simple file searches faster, I separated the functional entries on the UI.

### 🚀 New Features

- **Search modes are finally split**: I added a standalone "AI Mode" toggle in the search box. By default, hitting Enter triggers a lightning-fast keyword exact search. When you only remember the vague meaning of something, you can click "AI Mode" to let the LLM help you find it.
- **Localized quick stat prompts**: During normal keyword searches, we no longer wait around for the cloud LLM to generate a "smart interpretation." Instead, the frontend quickly prompts "Found X related results for you," instantly speeding up the response time for normal searches.

## [1.5.0] - 2026-04-08

In this version, I officially introduced LLM "intent understanding" into the main search pipeline. As long as you have a DashScope Key configured, the system will automatically guess what you're trying to search for. It's starting to feel more and more like a "smart assistant."

### 🚀 New Features

- **Search files with natural language**: You can now speak to it plainly. The system translates your plain text into structured query conditions. If the model realizes you're actually looking for a specific file, it automatically triggers `exact_focus` to take the exact-search shortcut. I also optimized the cache keys to isolate different search modes.

### 🐞 Bug Fixes

- Fixed an issue where the "Guess you're looking for" badge was randomly assigned. It now only shows up on the most relevant, top-ranked result.
- Fixed a bug where, during consecutive searches, the "smart interpretation" from the previous round would bleed into the new search.
- Added fault tolerance to backend endpoints. If it receives weird JSON data, it will gently return a 400 instead of crashing the service with a 500.

## [1.4.0] - 2026-04-01

This was a massive overhaul of the underlying infrastructure. I thoroughly cleaned up the code and natively integrated MWeb notes, which I use all the time.

### 🚀 New Features

- **Zero-config MWeb integration**: Finally, no more wrestling with tedious export scripts. Now, just set `ENABLE_MWEB=True` in the config, and the program automatically takes over scanning and indexing your MWeb library. Truly out-of-the-box.
- **Config and infrastructure standardization**: Introduced strongly-typed `settings.py` to consolidate environment variables and configs that used to be scattered everywhere, complete with fallback handling.
- **Decoupled core modules**: Extracted all the logic that used to be crammed into the routing file into standalone services (`services/`). File management, search concurrency, and health checks all have their own specific jobs now. It looks so much cleaner.

### 🛡 Security & Stability

- **Strict request validation**: Shipped `request_validation.py`, so you no longer have to worry about illegal search requests crashing the backend.
- **Path traversal prevention**: Added strict rules to the low-level `file_access.py`. Any attempt to read files outside the indexed directories is ruthlessly blocked, keeping the local host secure.

## [1.3.3] - 2026-03-31

### 🛠 Improvements

- **Makefile additions**: Added a `make help` target, so it's easy to look up commands when you forget them.
- **Documentation cleanup**: Added English UI design documentation and aligned variable descriptions across various supporting docs and tables.

## [1.3.2] - 2026-03-31

### 🚀 UI Experience

- **A fresh coat of paint**: Revamped the visuals and interactions of the search page. Borrowed design guidelines from Apple and Google to optimize typography, the pill-shaped search box, focus feedback, filter cards, and button sizes. Supported system-level reduced motion settings. Overall, it looks much cleaner and more modern without breaking existing API behavior.

## [1.3.1] - 2026-03-27

### 🐞 Bug Fixes

- **Fixed a ChromaDB upgrade disaster**: Upgraded `chromadb` to 1.5.5. Previously, under the new Python 3.14 and Pydantic 2, the old Chroma would throw a bunch of type inference errors and break the incremental indexer. Switched to Pydantic v2 validators, and everything is back to normal.

## [1.3.0] - 2026-03-26

### 🛠 Improvements

- **Bilingual documentation bundle**: Completed bilingual (English/Chinese) versions of all core docs (including README, install guides, tech manual, and changelog) with toggle links at the top. Should be much friendlier for folks used to reading English docs.
- **Entry point cleanup**: Standardized `README.md` as the English entry and `README.zh-CN.md` as the Chinese entry, killing off redundant files.

## [1.2.3] - 2026-03-26

### 🛠 Improvements

- **Fixed script launch errors**: Changed all relative imports in the incremental indexing script to absolute imports, fixing the occasional `ImportError` when running the script directly.
- **Added Makefile shortcuts**: Added a Makefile to the root directory. Now you can just run `make app` or `make index` to start the service, check status, or run indexing, instead of typing out long script paths every time.

## [1.2.1] - 2026-03-23

### 🛠 Improvements

- **Logs finally rotate daily**: The old, ever-growing single log file was way too inelegant. Configured Gunicorn's rotation strategy so app and error logs split daily (kept for 90 days). Launchd daemon outputs now write daily as well.
- Added daily log rotation support for dev mode too.
- **Note**: Upgraders remember to re-run `scripts/install_launchd_wrappers.sh` to update the background daemon.

## [1.2.0] - 2026-03-23

### 🛠 Architecture Tweaks

- **Moved code around**: Reorganized the project layout. Docs went into `docs/`, scripts into `scripts/`, all business code into `everythingsearch/`, and cache/data unified into `data/`. The structure looks much better now.
- **Standardized entry points**: Unified all launch commands to standard module launches like `python -m everythingsearch.app`.
- Changed frontend icon referencing so it doesn't hardcode static paths anymore.

## [1.1.0] - 2025-03-23

### 🚀 New Features

- **Health status probe**: Added a `GET /api/health` endpoint to easily check how the vector db is doing, document counts, and memory cache footprint (just don't expose it to the public internet).
- **Manual cache clear endpoint**: Added `POST /api/cache/clear`. If you just finished indexing and don't want to restart the service, one click instantly clears the query cache.
- **Added timeout protection to search**: Used system alarms to add a ~30-second timeout to single searches, preventing deadlocks or slow queries from freezing the process.
- **Refactored Embedding cache**: Switched to SQLite WAL mode and connection pooling, massively improving query and write performance.

## [1.0.0] - Previously

The initial public release. Implemented local file semantic search based on ChromaDB, incremental indexing, and a minimalist Web UI. This is where the dream started.
