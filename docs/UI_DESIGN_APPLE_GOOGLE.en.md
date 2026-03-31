# EverythingSearch Web UI: Apple × Google Style Refresh

[English](UI_DESIGN_APPLE_GOOGLE.en.md) | [中文](UI_DESIGN_APPLE_GOOGLE.md)

## Goals

Without changing **any functionality or JavaScript behavior**, align the single-page template `everythingsearch/templates/index.html` with common patterns from **Apple Human Interface Guidelines** and **Google Material Design 3**: clear hierarchy, readable typography, soft surfaces and shadows, and explicit focus and touch feedback.

## Scope

- Only embedded `<style>` in that template and non-behavioral class names as needed (no new script logic in this design).
- No external fonts or CDNs; keep the system font stack (`-apple-system`, `Roboto` on Android, `Segoe UI`, `PingFang SC`, etc.) for local service use and privacy.

## Design Tokens


| Token | Role |
| ----- | ---- |
| `--bg` / `--bg-card` | Page and card surfaces; light theme uses Material-like neutrals (`#f8f9fa` / `#fff`); dark theme keeps clear layering. |
| `--text` / `--text-secondary` | Primary and secondary copy; secondary approximates M3 `on-surface-variant` contrast (`#5f6368`). |
| `--border` / `--border-strong` | Dividers and input outlines; softer default strokes, primary-colored outline on focus. |
| `--accent` | Keeps the existing brand-blue bias (`#0071e3`), aligned with Apple link blue, to avoid muddying semantic colors. |
| `--accent-container` | M3-style primary container fill for sidebar selection and chip hover/selected backgrounds. |
| `--shadow-*` | Combines light Google-style elevation with Apple-like diffuse shadows; cards lift slightly on hover. |
| `--radius-sm` / `--radius-md` / `--radius-lg` / `--radius-pill` | Shared radii: ~10px controls, ~14–16px cards, pill-shaped search field. |


## Component-Level Notes

1. **Search field**: Higher pill radius (`border-radius: 26px` in implementation), focus ring via `box-shadow` plus thin border; icon and padding sized for comfortable hit area; shortcut badge uses surface background and small pill radius.
2. **Sidebar**: Lighter right-edge treatment (border + subtle shadow); history rows use rounded backgrounds with a 3px left accent; hover/active use `accent-container` instead of heavy flat fills.
3. **Sort / source / date**: Chip styling—`border-radius: 9999px`, `min-height: 32px`, horizontal padding ~14px; selected state stays **filled primary + high-contrast text** to match existing logic, with refined radius and spacing.
4. **Result cards**: Slightly larger radius and padding; layered elevation shadows; hover uses `translateY(-2px)` and stronger shadow (transitions respect `prefers-reduced-motion: reduce`).
5. **Pagination**: Round page controls kept; stronger `focus-visible` and hover states.
6. **A11y & motion**: `button` / `input` get `:focus-visible` treatment; `prefers-reduced-motion: reduce` shortens or disables motion; smooth scrolling on `html` only when motion is allowed.

## Acceptance

- Search, history, sort, filters, pagination, open / reveal behave as before.
- Light / dark `prefers-color-scheme` contrast remains acceptable.
- Keyboard Tab shows visible focus; no strong motion under system “reduce motion”.
