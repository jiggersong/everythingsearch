# EverythingSearch Web UI：Apple × Google 风格优化方案

[English](UI_DESIGN_APPLE_GOOGLE.en.md) | [中文](UI_DESIGN_APPLE_GOOGLE.md)

## 目标

在**不改变任何功能与 JS 行为**的前提下，将单页模板 `everythingsearch/templates/index.html` 的视觉与交互对齐 **Apple Human Interface Guidelines** 与 **Google Material Design 3** 的共性：清晰层级、易读排版、柔和表面与阴影、明确的焦点与触控反馈。

## 技术范围

- 仅修改该模板内嵌的 `<style>` 与必要的无行为类名（本方案不新增脚本逻辑）。
- 不引入外部字体或 CDN，继续使用系统字体栈（`-apple-system`、`Roboto` 在 Android、Segoe UI、`PingFang SC` 等），兼顾本地服务与隐私。

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


## 组件级改动要点

1. **搜索框**：胶囊形圆角（实现为 `border-radius: 26px`）、聚焦环 `box-shadow` + 细描边；图标与内边距按舒适点击区域对齐；快捷键徽标使用表面色与小圆角 pill。
2. **侧栏**：减轻右侧重阴影，采用 `border` + 极轻 shadow；历史项使用圆角背景条 + 左侧 3px 指示，hover/active 使用 `accent-container` 而非高饱和铺满。
3. **排序 / 来源 / 日期**：Chip 样式——`border-radius: 9999px`、`min-height: 32px`、`padding` 水平 14px；选中态为「主色描边 + 浅容器底 + 主色文字」或「实心主色 + 白字」二选一以保持对比；本方案采用 **实心主色 + 白字** 与现有逻辑一致，仅优化圆角与间距。
4. **结果卡片**：略增大圆角与内边距；阴影使用双层 elevation；hover 时 `translateY(-2px)` 与阴影加深（在 `prefers-reduced-motion: reduce` 下关闭动画与过渡）。
5. **分页**：圆形页码保留，增强 `focus-visible` 环与 hover 状态。
6. **无障碍与交互**：`button` / `input` 等补充 `:focus-visible`；`prefers-reduced-motion: reduce` 下缩短或关闭动效；仅在系统允许动效时 `html` 使用平滑滚动。

## 验收

- 搜索、历史、排序、筛选、分页、打开/ reveal 等行为与改前一致。
- 浅色/暗色 `prefers-color-scheme` 下对比度可接受。
- 键盘 Tab 可见焦点；系统「减少动态效果」下无强动画。

