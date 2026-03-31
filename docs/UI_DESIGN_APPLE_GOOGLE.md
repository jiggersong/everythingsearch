# EverythingSearch Web UI：Apple × Google 风格优化

[English](UI_DESIGN_APPLE_GOOGLE.en.md) | [中文](UI_DESIGN_APPLE_GOOGLE.md)

## 原则

视觉与交互对齐 **Apple Human Interface Guidelines** 与 **Google Material Design 3** 的共性：清晰层级、易读排版、柔和表面与阴影、明确的焦点与触控反馈。

## 设计令牌


| 令牌                                                              | 用途                                                      |
| --------------------------------------------------------------- | ------------------------------------------------------- |
| `--bg` / `--bg-card`                                            | 页面背景与卡片表面；浅色偏 Material 中性灰（`#f8f9fa` / `#fff`），暗色保持分层。  |
| `--text` / `--text-secondary`                                   | 主文与次级说明；次级色采用接近 M3 `on-surface-variant`（`#5f6368`）的对比度。 |
| `--border` / `--border-strong`                                  | 分隔线与输入框描边；弱化默认「硬线」，聚焦时用主色描边。                            |
| `--accent`                                                      | 保留既有品牌蓝倾向（`#0071e3`），与 Apple 链接色一致，避免功能色语义混乱。           |
| `--accent-container`                                            | M3 风格「主色容器」浅底，用于侧栏选中、Chip 选中态背景替代纯填充时的刺眼感。              |
| `--shadow-`*                                                    | 组合 Google 组件轻微 elevation 与 Apple 漫反射阴影，卡片 hover 仅微抬升。   |
| `--radius-sm` / `--radius-md` / `--radius-lg` / `--radius-pill` | 统一圆角：小控件 10px、卡片 14–16px、搜索框胶囊形。                        |


