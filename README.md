# EverythingSearch

[English](README.md) | [中文](README.zh-CN.md)

EverythingSearch is a **local semantic file search engine for macOS**, comparable in spirit to **Everything** on Windows: use **natural language or keywords** to search local documents, code, materials, and notes.

## Core Capabilities

- **Ask the way you remember**: Use a full sentence in natural language or just a few keywords; get fast answers over indexed files and fewer “macOS Search missed it” moments.
- **Filenames and body text together**: Matches aren’t limited to filenames—headings and document text count too; results that already show your clues in the name or title tend to rank higher so you scroll less.
- **Narrow the hunt**: Filter by folder and by modified or created time, or switch to a filename-focused mode when that’s all you recall.
- **Comfortable in the browser**: Search and skim results in a local web UI with a clear layout and a roomy results pane; turn on optional AI-assisted interpretation when you have a working model endpoint configured.
- **One heavier build, then mostly incremental**: The first full index scans the disk and can take time; indexing now prints file-scale, token, and time estimates first, then progress every 30 seconds. Later runs update only what changed, keeping day-to-day waits and disk churn manageable.
- **Your data stays primarily local**: Indexes and vectors live on your Mac by default. Text is sent to your configured model service only when building embeddings or when you use smart search / interpretation features; behavior without an API key is described in [NL_SEARCH_AND_WEB_UI.en.md](docs/NL_SEARCH_AND_WEB_UI.en.md).
- **MWeb in one toggle**: If you keep notes in MWeb, flip one setting to fold that library into the same index.
- **Supercharge your Agent (CLI Support)**: I frequently tinker with LLM agents like OpenClaw, so I wrote a clean, JSON-outputting CLI interface for this search engine. Just paste a simple prompt, and your agent instantly gains "local eyes" to find files on your machine!

---

## Quick Start

```bash
git clone https://github.com/jiggersong/everythingsearch.git
cd everythingsearch
./scripts/install.sh
```

## Agent / OpenClaw Installation (Non-interactive)

`./scripts/install.sh` is designed for humans and is intentionally interactive.  
If OpenClaw (or any Agent) installs this project, **do not rely on the interactive prompts**. Use this non-interactive flow instead:

```bash
git clone https://github.com/jiggersong/everythingsearch.git
cd everythingsearch

# 1) Create venv and install dependencies
python3.11 -m venv venv || python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements/base.txt

# 2) Prepare config.py
cp -n etc/config.example.py config.py

# 3) Fill required config fields NON-interactively
# Replace placeholders before running:
export ES_API_KEY="sk-xxxx"
export ES_TARGET_DIR="/Users/you/Documents"
./venv/bin/python - <<'PY'
from pathlib import Path
import os
import re

path = Path("config.py")
text = path.read_text(encoding="utf-8")

def set_line(src: str, key: str, value: str) -> str:
    return re.sub(rf'^{key}\s*=.*$', f'{key} = "{value}"', src, flags=re.MULTILINE)

text = set_line(text, "MY_API_KEY", os.environ["ES_API_KEY"])
text = set_line(text, "TARGET_DIR", os.environ["ES_TARGET_DIR"].rstrip("/"))
path.write_text(text, encoding="utf-8")
print("config.py updated")
PY

# 4) First index build
make index

# 5) Register background web service + scheduled incremental indexing (~every 30 min, no prompts)
./scripts/install_launchd_wrappers.sh

# 6) Verify (install_launchd_wrappers bootstraps jobs via launchctl)
./scripts/run_app.sh status
make index-svc-status
curl -s http://127.0.0.1:8000/api/health
```

### Background service and scheduled indexing (recommended)

`./scripts/install_launchd_wrappers.sh` performs these steps **non-interactively**:

- Derives a unique launchd Label from the install directory (safe for multiple clones)
- Writes plists under `~/Library/LaunchAgents/` and registers two jobs with `launchctl bootstrap`:
  - **Search web service**: runs at login and stays alive (`RunAtLoad` + `KeepAlive`)
  - **Scheduled incremental index**: runs `everythingsearch.incremental` every **30 minutes** by default (`StartInterval=1800`)

This matches the optional launchd steps in `install.sh` but requires **no** terminal Q&A. Scheduling does **not** need a separate permission toggle in System Settings (unlike Full Disk Access).

Optional: change the index interval (default 30 minutes):

```bash
make index-svc-interval MIN=30
```

### Agent guardrails

- **Never** call `./scripts/install.sh` unless the Agent can handle terminal interaction reliably.
- Always use `./venv/bin/python` and `./venv/bin/pip` (avoid system Python ambiguity).
- Keep all paths absolute in Agent commands.
- If `TARGET_DIR` is empty or wrong, indexing will succeed with little/no useful data. Validate it first.
- **Do not skip** `./scripts/install_launchd_wrappers.sh`; otherwise `./scripts/run_app.sh start` fails (launchd not registered) and file changes will not be indexed automatically.
- For a typical `TARGET_DIR` under `~/Documents`, **Full Disk Access is usually not required**; only enable MWeb (`ENABLE_MWEB`) or index paths under `~/Library` should you follow [INSTALL.en.md](docs/INSTALL.en.md) and have the **user** grant Full Disk Access manually (Agents cannot click System Settings).
- If your Agent can call localhost HTTP, integrate via [`skills/everythingsearch-local/SKILL.md`](skills/everythingsearch-local/SKILL.md) and prefer `GET /api/search` for deterministic retrieval.

## Version Upgrade

If you already have an older version (v1.0.0 or later) installed, follow these steps to upgrade.

### Step 1: Download the new version to a separate directory

**Do not overwrite your old installation.** Download (or `git clone`) the new version into a **brand-new directory**:

```bash
# Option 1: git clone
git clone https://github.com/jiggersong/everythingsearch.git ~/Downloads/EverythingSearch-new
cd ~/Downloads/EverythingSearch-new

# Option 2: Download the release archive and unzip
# If you unzipped to ~/Downloads/EverythingSearch-new
cd ~/Downloads/EverythingSearch-new
```

### Step 2: Run the upgrade script

From the new directory, run the upgrade script — it will automatically find your old installation (default location `~/Documents/code/EverythingSearch`):

```bash
./scripts/upgrade.sh
```

If your old project is installed somewhere else, specify its path:

```bash
./scripts/upgrade.sh /path/to/your/old/installation
```

### Step 3: Follow the prompts

The script will guide you through:
- Showing the detected old version and confirming the upgrade
- Syncing new code to your old project location (your config and data are preserved)
- Backing up key old data, migrating selected configuration fields, cleaning up incompatible indexes, and updating Python dependencies
- Asking whether to rebuild the index now (**recommended: say yes** and keep the terminal open while it runs)

### Step 4: Clean up

After the upgrade completes and everything works:
- **New directory** (e.g. `~/Downloads/EverythingSearch-new`): no longer needed — delete it
- **Old project directory** (e.g. `~/Documents/code/EverythingSearch`): now updated to the latest version — keep using this one
- **Backup directory** (`upgrade_backups_timestamp/` inside the project): delete after confirming everything is fine

See [INSTALL.en.md](docs/INSTALL.en.md) §9 for details.

## Common Commands

```bash
make help          # list all make targets with short descriptions
make index         # incremental indexing with scale/token estimates and 30s progress
make index-full    # full reindex with scale/token estimates and 30s progress
make app           # run app in the foreground
make search q="keyword"  # CLI search (JSON output)
make app-status    # status of launchd-managed app
make app-restart   # restart launchd-managed app
make app-stop      # stop launchd-managed app

# Or use the CLI module directly
python -m everythingsearch search "your query here" --json
```

## System Permissions & Automation

After installation, complete these three system-level steps so the service can run reliably in the background:


| Feature                     | Description                                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Auto-start on login**     | The search service (Web UI) is started by launchd after you sign in—no manual launch.                        |
| **Scheduled index updates** | Incremental indexing runs every 30 minutes by default, keeping the index close to disk state.                |
| **Full Disk Access**        | Grant Python access to protected locations (e.g. some MWeb data paths) to avoid repeated permission prompts. |


> For detailed steps, see `[PROJECT_MANUAL.en.md](docs/PROJECT_MANUAL.en.md)` §6.5 “System Permissions & Automation Setup”.

## Documentation Matrix


| No  | Document                                                                           | Role                              | Best For                                                    | What You Get                                                                                                                  |
| --- | ---------------------------------------------------------------------------------- | --------------------------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 1   | `[INSTALL.en.md](docs/INSTALL.en.md)`                                              | Installation and operations guide | First install, new machine, environment setup               | Prerequisites, API key, install flow, launchd wrappers, day-to-day commands                                                   |
| 2   | `[PROJECT_MANUAL.en.md](docs/PROJECT_MANUAL.en.md)`                                | Technical reference manual        | Development, maintenance, customization                     | Architecture, module boundaries, config matrix, indexing/search flow, tuning and deployment                                   |
| 3   | `[UI_DESIGN_APPLE_GOOGLE.en.md](docs/UI_DESIGN_APPLE_GOOGLE.en.md)`                | Web UI design notes               | UI upkeep, HIG/Material alignment, accessibility and motion | Design principles and tokens; bilingual pages linked at the top                                                               |
| 4   | `[NL_SEARCH_AND_WEB_UI.en.md](docs/NL_SEARCH_AND_WEB_UI.en.md)`                    | NL search behavior notes          | Smart search integration, default fallback, API checks      | Intent route, interpretation route, `exact_focus`, rate limits, behavior without a key                                        |
| 5   | `[SEARCH_ACCURACY_TECHNICAL_DESIGN.en.md](docs/SEARCH_ACCURACY_TECHNICAL_DESIGN.en.md)` | Accuracy technical design          | Reviewing the next search architecture rebuild              | FTS5, vector recall, RRF, remote rerank, file aggregation, benchmark plan, and implementation order                          |
| 6   | `[OPENCLAW_INTEGRATION.md](docs/OPENCLAW_INTEGRATION.md)`                          | Agent integration guide           | Giving OpenClaw local search powers                         | Foolproof system prompt configuration, test commands, easy for beginners                                                      |
| 7   | `[skills/everythingsearch-local/SKILL.md](skills/everythingsearch-local/SKILL.md)` | Agent Skill (open source)         | Cursor / Claude Code integration with the local HTTP API    | Example calls for search and interpretation routes, `EVERYTHINGSEARCH_BASE`, safety and fallbacks; pairs with the manual §3.1 |


## Agent Skill (open source)

`[skills/everythingsearch-local/SKILL.md](skills/everythingsearch-local/SKILL.md)` explains how **Cursor, Claude Code, and other Agent Skill–capable tools** can call this service’s HTTP API (hybrid search, natural-language search, intelligent interpretation, file reads, etc.). For Cursor, copy or symlink that folder to `.cursor/skills/everythingsearch-local/` in your workspace. See `[PROJECT_MANUAL.en.md](docs/PROJECT_MANUAL.en.md)` §3.1 for details.

## Technical Reference Manual Scope

`[PROJECT_MANUAL.en.md](docs/PROJECT_MANUAL.en.md)` is the project's core technical reference manual. It covers:


| Area             | Highlights                                                                            |
| ---------------- | ------------------------------------------------------------------------------------- |
| Foundations      | Project goals, core capabilities, overall architecture                                |
| System design    | Architecture diagram, stack, repository layout                                        |
| Module internals | Responsibilities of `app`, `retrieval.pipeline`, `indexer`, `incremental`, `embedding_cache`      |
| Runtime behavior | Configuration matrix, indexing/search lifecycle, HTTP API surface, Agent Skill (§3.1) |
| Evolution        | Publishable entry point for the accuracy-first search redesign                        |
| Operations       | launchd service model, common commands, tuning, fresh-deployment checklist            |


Use the language links at the top of this page to switch to Chinese.

## License

This project is licensed under the [MIT License](LICENSE).
