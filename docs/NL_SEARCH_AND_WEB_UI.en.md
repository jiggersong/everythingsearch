# Natural-Language Search and Web UI Behavior

[English](NL_SEARCH_AND_WEB_UI.en.md) | [中文](NL_SEARCH_AND_WEB_UI.md)

This document summarizes the **current implementation** and stays aligned with the search sections in `docs/PROJECT_MANUAL.en.md`. Files under `dev_docs/` are development-process notes; the externally relevant current behavior is defined by this document and the project manual.

## 1. Goals

- When a DashScope API key is configured, the web UI uses the default smart flow: intent parsing -> structured search -> optional interpretation.
- When no key is configured, the browser does **not** call `/api/search/nl` or interpretation endpoints; it falls back to `GET /api/search`.
- When users explicitly ask for literal / exact matching, the model can emit `slots.match_mode = "exact_focus"` so the backend uses a keyword-first path; if nothing survives, search falls back to the normal hybrid pipeline.

## 2. Components and Data Flow

| Stage | Module | Notes |
| --- | --- | --- |
| Intent | `everythingsearch/services/nl_search_service.py` | DashScope JSON with `slots.q`, optional `match_mode`, `source`, dates, and limit |
| Search | `everythingsearch/services/search_service.py` -> `search_core` | Passes `SearchRequest.exact_focus` into `search.py` |
| Hybrid / exact | `everythingsearch/search.py` | `exact_focus=True` runs `_keyword_fallback` first and falls back to vector + keyword hybrid when needed |
| Interpretation | `everythingsearch/services/search_interpret_service.py` | Streaming and non-streaming summary over the current hit list |
| Rate limiting | `everythingsearch/infra/rate_limiting.py` | `RATE_LIMIT_NL_PER_MIN`, `RATE_LIMIT_INTERPRET_PER_MIN` |
| Page | `everythingsearch/templates/index.html` | `smart_search_available` decides whether the browser uses NL routes |

## 3. API Summary

- **`POST /api/search/nl`**
  - Request body: `message`, optional `sidebar_source`, `date_field`, `date_from`, `date_to`, `limit`
  - Success: `kind: search_results`; `results` matches `/api/search`; `resolved` includes normalized `source`, `match_mode`, `exact_focus`, and related fields

- **`GET /api/search`**
  - No `exact_focus` query parameter; only the NL route sets `SearchRequest.exact_focus`

- **`POST /api/search/interpret` / `POST /api/search/interpret/stream`**
  - Consume the current search results and produce a short explanation
  - Require an API key
  - Share per-IP rate limiting

## 4. Related Configuration

`NL_SEARCH_ENABLED` has been removed. NL-related settings now include:

- `NL_INTENT_MODEL`
- `SEARCH_INTERPRET_MODEL`
- `NL_TIMEOUT_SEC`
- `INTERPRET_TIMEOUT_SEC`
- `NL_MAX_MESSAGE_CHARS`
- `INTERPRET_MAX_RESULTS`
- `RATE_LIMIT_NL_PER_MIN`
- `RATE_LIMIT_INTERPRET_PER_MIN`
- `TRUST_PROXY`

See `PROJECT_MANUAL.en.md` for the full configuration table.

## 5. Known Trade-offs

- Intent quality still depends on model output quality; invalid `match_mode` values are normalized to `balanced`.
- `search_interpret_service.py` still keeps a generic fallback catch for unexpected non-DashScope failures; route-level input handling is separate from that internal fallback.
