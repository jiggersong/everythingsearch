# EverythingSearch Web UI: Apple × Google Style Optimization

[English](UI_DESIGN_APPLE_GOOGLE.en.md) | [中文](UI_DESIGN_APPLE_GOOGLE.md)

## Principles

Align visuals and interaction with the shared expectations of **Apple Human Interface Guidelines** and **Google Material Design 3**: clear hierarchy, readable typography, soft surfaces and shadows, and explicit focus and touch feedback.

## Design Tokens


| Token                                                             | Role                                                                                    |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `--bg` / `--bg-card`                                              | Page and card surfaces; light theme leans on Material-like neutrals (`#f8f9fa` / `#fff`); dark theme keeps clear layering. |
| `--text` / `--text-secondary`                                     | Primary and secondary text; secondary approximates M3 `on-surface-variant` contrast (`#5f6368`). |
| `--border` / `--border-strong`                                    | Dividers and input outlines; softer default strokes, primary-colored outline on focus. |
| `--accent`                                                        | Keeps the existing brand-blue bias (`#0071e3`), aligned with Apple link blue, to avoid muddying semantic colors. |
| `--accent-container`                                              | M3-style primary container fill for sidebar selection and chip selected states, avoiding harsh solid fills. |
| `--shadow-`*                                                      | Combines light Google-style elevation with Apple-like diffuse shadows; cards lift slightly on hover. |
| `--radius-sm` / `--radius-md` / `--radius-lg` / `--radius-pill`   | Shared radii: ~10px controls, ~14–16px cards, pill-shaped search field.               |

