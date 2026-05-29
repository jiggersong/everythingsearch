# OpenClaw Integration Guide for EverythingSearch

This guide helps you connect **OpenClaw** (or any Agent that can run shell commands or call localhost HTTP) to EverythingSearch local search.

For the full HTTP API reference, see [`skills/everythingsearch-local/SKILL.md`](../skills/everythingsearch-local/SKILL.md). For **non-interactive OpenClaw install (including scheduled incremental indexing)**, see [README.md](../README.md) § “Agent / OpenClaw Installation”. For “file not found” troubleshooting, see [INSTALL.md](INSTALL.md) §7.

---

## Step 1: Verify your environment

1. Installation complete and at least one index build done. If OpenClaw installed the project, follow [README.md](../README.md) (includes `./scripts/install_launchd_wrappers.sh` for ~30-minute incremental indexing); humans may use interactive [INSTALL.md](INSTALL.md) / `install.sh` instead.
2. Use the **project virtualenv Python** from the install directory:

```bash
cd /path/to/your/EverythingSearch
PY=./venv/bin/python
```

3. **DashScope API key** (required for CLI search)  
   The `search` CLI runs intent recognition first (same as the web “smart search”). Set `MY_API_KEY` in `config.py`. Without a key, the CLI returns a `MISSING_API_KEY`-style error.

4. **HTTP service and scheduled indexing** (recommended if your Agent can use `curl` — see “Option B” below):

```bash
# If launchd is not registered yet (non-interactive; web service + ~30 min incremental index):
./scripts/install_launchd_wrappers.sh

./scripts/run_app.sh status
make index-svc-status
curl -s http://127.0.0.1:8000/api/health
```

### Smoke tests (any one passing is enough)

**A. Health check (service only)**

```bash
curl -s http://127.0.0.1:8000/api/health | head -c 200
```

**B. Direct HTTP search (short keywords work; no LLM intent step)**

```bash
curl -sG "http://127.0.0.1:8000/api/search" \
  --data-urlencode "q=architecture" \
  --data-urlencode "limit=3"
```

You should get JSON with a `results` array (empty is OK if the structure is valid).

**C. CLI natural-language search (requires DashScope key)**

```bash
$PY -m everythingsearch search "find documents about system architecture" --json
```

On success, `stdout` is a single JSON line with a `results` array. **Do not** self-test with a single vague word like `test` or `architecture` alone — the intent layer may return `out_of_scope` and exit non-zero; that does not mean the service is broken.

---

## Step 2: Choose an integration path

### Option A: CLI (when OpenClaw can only run shell commands)

**Syntax:**

```bash
cd /path/to/your/EverythingSearch
./venv/bin/python -m everythingsearch search "<query>" --json [--limit N] [--source all|file|mweb]
```

| Flag | Description |
| --- | --- |
| `<query>` | Quoted; natural language is supported — include a concrete topic, filename, or name |
| `--json` | **Required** for machine-readable stdout |
| `--limit` | Optional, default 10, max 200 |
| `--source` | Optional: `all`, `file`, or `mweb` (MWeb requires `ENABLE_MWEB=True`) |

**Success JSON shape:**

```json
{
  "query": "normalized search terms",
  "results": [
    {
      "filepath": "/absolute/path/file.pdf",
      "score": 0.85,
      "snippet": "preview of the hit…",
      "mtime": 1710934301.0
    }
  ]
}
```

- `filepath`: use directly for read/open/reveal actions.
- `snippet`: excerpt from the pipeline (`preview`/`content`); if empty, read `filepath` with your Agent’s file tools.

**Failure JSON:**

```json
{
  "error": "message",
  "capabilities": ["local file keyword and filter search"]
}
```

Common causes: query too short for intent layer, missing API key, index not built, DashScope unreachable.

---

### Option B: HTTP API (recommended when OpenClaw can reach localhost)

Default base URL: `http://127.0.0.1:8000` (see `config.PORT` or `scripts/.launchd_instance`).

| Use case | Endpoint |
| --- | --- |
| Keywords / short phrases, no LLM | `GET /api/search?q=...&limit=30` |
| Full-sentence NL + exact-focus | `POST /api/search/nl` (key required) |
| Summarize current hits | `POST /api/search/interpret` (key required) |
| Text preview | `GET /api/file/read?filepath=...` |

Example:

```bash
BASE=http://127.0.0.1:8000
curl -sG "$BASE/api/search" --data-urlencode "q=budget excel" --data-urlencode "limit=20"
```

HTTP results use `preview`, not `snippet`. See [`skills/everythingsearch-local/SKILL.md`](../skills/everythingsearch-local/SKILL.md) for full curl examples, rate limits, and fallbacks.

---

## Step 3: Configure OpenClaw system prompt

Paste the block below into OpenClaw’s **System Prompt** or **Tools** settings. Prefer Option B (`curl`) if HTTP is available; otherwise use Option A.

```text
# Tool: EverythingSearch local retrieval

## Prerequisites
- Working directory: /path/to/your/EverythingSearch
- Python: ./venv/bin/python
- CLI search needs a DashScope API key; without it, use curl GET /api/search (start service with ./scripts/run_app.sh start)

## Option A — CLI (only if HTTP is unavailable)
./venv/bin/python -m everythingsearch search "<query>" --json [--limit 20] [--source all]

Rules:
- Quote <query>; include a concrete topic/filename/name — avoid lone words like "test".
- Always pass --json; parse stdout JSON only, ignore stderr.
- Read filepath and snippet from results[]; if snippet is empty, read filepath.

## Option B — HTTP (preferred)
curl -sG "http://127.0.0.1:8000/api/search" --data-urlencode "q=<keywords>" --data-urlencode "limit=30"
Read filepath and preview from results[].

## Forbidden
When the index is available, do not use find / mdfind / locate / glob instead of EverythingSearch.

## Workflow
1. On local document questions, search first, then answer.
2. Trust filepath from API/CLI even if the terminal shows mojibake for CJK paths.
3. If nothing matches: check TARGET_DIR and index — see docs/INSTALL.md §7.
```

---

## Step 4: Try it and troubleshoot

**Example prompts:**

- “Find documents on my machine about product architecture evolution.”
- “Which file implements user login?”
- “Exact search for xlsx files whose filename contains budget.”

**If search returns nothing:**

1. File still under `TARGET_DIR` and indexed — see [INSTALL.md](INSTALL.md) §7 (SQL checks).
2. CLI `out_of_scope` on very short queries — use a fuller sentence or `GET /api/search`.
3. Full filenames like `report.pdf` failing — run `make index-full` or search without the extension.
4. Duplicate rows for one file — run `make index-full` to rebuild consistent `file_id` metadata.

**Further reading:**

- [`skills/everythingsearch-local/SKILL.md`](../skills/everythingsearch-local/SKILL.md) — full Agent HTTP manual  
- [`docs/PROJECT_MANUAL.md`](PROJECT_MANUAL.md) §3.2 — CLI and architecture  
- [`docs/NL_SEARCH_AND_WEB_UI.md`](NL_SEARCH_AND_WEB_UI.md) — NL search and web UI behavior
