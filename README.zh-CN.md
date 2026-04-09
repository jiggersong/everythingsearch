# EverythingSearch

[English](README.md) | [中文](README.zh-CN.md)

EverythingSearch 是运行在 macOS 上的**本地文件语义搜索引擎**，能力与 Windows 下的 **Everything** 相近：支持用**自然语言或关键词**检索本地文档、代码、资料与笔记。

## 核心能力

- **文件搜索**：支持自然语言或关键词，对已索引文件快速检索，秒级返回，缓解 macOS 自带搜索常不够好用的问题。
- **混合索引**：同时索引文件内容与文件名，正文里的信息也能被找到。
- **位置加权**：关键词出现在文件名、标题中的结果排序更靠前。
- **缓存机制**：首次全量索引需全盘扫描，耗时较长；之后按文件变更增量更新，日常维护成本低、速度快。
- **隐私与数据流**：索引与向量数据默认保存在本机。构建索引时会将待向量化的文本片段发往 DashScope（或你所配置的模型服务）以生成 embedding；在已配置 API Key 且使用网页 NL 搜索时，还会将当前查询及精简后的结果摘要用于意图解析与可选的智能解读。未配置 Key 时，前端不调用 NL 链路，行为见 [NL_SEARCH_AND_WEB_UI.md](docs/NL_SEARCH_AND_WEB_UI.md)。
- **Web 界面**：在浏览器中搜索，交互类似用搜索引擎查网页，但数据在本地；支持按文件时间过滤，结果更可控。
- **MWeb 支持**：若使用 MWeb 管理笔记与 Markdown，在配置中开启一项即可接入并索引 MWeb 内容。

---

## 快速开始

```bash
git clone https://github.com/jiggersong/everythingsearch.git
cd everythingsearch
./scripts/install.sh
```

## 常用命令

```bash
make help          # 列出全部 make 目标及一行说明
make index         # 增量索引
make index-full    # 全量重建索引
make app           # 前台运行应用
make app-status    # 查看 launchd 托管服务状态
make app-restart   # 重启常驻服务
make app-stop      # 停止常驻服务
```

## 系统权限与自动化

安装完成后，建议完成以下三项系统级配置，便于服务在后台稳定、免打扰运行：

| 功能 | 说明 |
| --- | --- |
| **开机自动启动** | 搜索服务（Web UI）在登录后由 launchd 自动拉起，无需手动启动。 |
| **定时更新索引** | 默认每 30 分钟执行增量索引，保持索引与磁盘接近同步。 |
| **完全磁盘访问** | 为 Python 授予受保护目录（如部分 MWeb 数据路径）的访问权限，避免每次运行都弹出授权提示。 |

> 详细步骤见 [PROJECT_MANUAL.md](docs/PROJECT_MANUAL.md) 第 6.5 节「系统权限与自动化设置」。

## 文档矩阵

| 序号 | 文档 | 角色 | 适用场景 | 可获得信息 |
| --- | --- | --- | --- | --- |
| 1 | [INSTALL.md](docs/INSTALL.md) | 安装与运维指南 | 首次安装、换新机、环境初始化 | 前置条件、API Key、安装流程、launchd 包装脚本、日常命令 |
| 2 | [PROJECT_MANUAL.md](docs/PROJECT_MANUAL.md) | 技术参考手册 | 开发、维护、二次改造 | 架构、模块边界、配置矩阵、索引/搜索流程、调优与部署 |
| 3 | [UI_DESIGN_APPLE_GOOGLE.md](docs/UI_DESIGN_APPLE_GOOGLE.md) | Web UI 设计说明 | 界面维护、HIG/Material 对齐、无障碍与动效 | 设计原则与设计令牌；中英文页顶互链 |
| 4 | [NL_SEARCH_AND_WEB_UI.md](docs/NL_SEARCH_AND_WEB_UI.md) | NL 搜索行为说明 | 智能搜索联调、默认回退、接口核对 | 意图接口、解读接口、`exact_focus`、限流、无 Key 时的行为 |

## 技术参考手册范围

[PROJECT_MANUAL.md](docs/PROJECT_MANUAL.md) 是项目的核心技术参考手册，主要覆盖：

| 范围 | 要点 |
| --- | --- |
| 基础 | 项目目标、核心能力、总体架构 |
| 系统设计 | 架构图、技术栈、仓库目录 |
| 模块 | `app`、`search`、`indexer`、`incremental`、`embedding_cache` 等职责 |
| 运行 | 配置矩阵、索引/搜索生命周期、HTTP API 能力 |
| 运维 | launchd 模型、常用命令、调优、从零部署检查项 |

可通过本页顶部链接切换至英文文档。

## 许可证

本项目采用 [MIT 许可证](LICENSE)。
