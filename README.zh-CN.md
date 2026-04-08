# EverythingSearch

[English](README.md) | [中文](README.zh-CN.md)

EverythingSearch 是一个运行在 macOS 上的**本地文件语义搜索引擎**，对应 Windows 下的 Everything 软件的能力，支持自然语言与关键词检索本地文档、代码、资料与笔记。

## 核心能力

- **文件搜索**：根据模糊的关键词快速检索全部文件，达到秒级返回，直接解决 Mac 搜索基本无用的困扰
- **混合索引**：同时索引文件内容和文件名，就算你要找的信息是在文件内容中，也一样可以搜到
- **位置加权**：关键词出现在文件名、标题中的结果会获得更高的排名
- **缓存机制**：只有在第一次安装完成后的索引重建需要花费比较长的时间全盘扫描，后续会根据文件变更增量构建索引，快如闪电
- **隐私保护**：索引数据保存在本机。DashScope 在索引阶段用于生成向量；当浏览器启用默认智能搜索时，还会接收当前查询文本与压缩后的结果摘要，用于意图识别和智能解读
- **Web界面**：直接在浏览器中搜索，像用 Google 找网络信息一样的找你的文件，简单友好。支持按照文件时间过滤，搜索更精准
- **MWeb 支持**：如果你正在使用 MWeb 作为笔记文件和 Markdown 编辑器，只需打开一个开关即可一键接管并索引你的 MWeb 内容

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
make index-full    # 全量重建
make app           # 前台运行
make app-status    # 查看常驻服务状态
make app-restart   # 重启常驻服务
make app-stop      # 停止常驻服务
```

## 系统权限与自动化设置

安装完成后，建议完成以下三步系统级配置，让服务在后台稳定无感运行：


| 功能         | 说明                                      |
| ---------- | --------------------------------------- |
| **开机自动启动** | 搜索服务（Web UI）在登录后由 launchd 自动启动，无需手动操作   |
| **定时更新索引** | 每 30 分钟自动执行增量索引，保持搜索内容最新                |
| **完全磁盘访问** | 授权 Python 访问受保护目录（如 MWeb 数据），避免每次出现权限弹框 |


> 详细操作步骤请参阅 [PROJECT_MANUAL.md](docs/PROJECT_MANUAL.md) 第 6.5 节「系统权限与自动化设置」。

## 文档矩阵


| 序号  | 文档 | 角色定位 | 适用场景 | 可获得信息 |
| --- | --- | --- | --- | --- |
| 1 | [INSTALL.md](docs/INSTALL.md) | 安装与运维指南 | 首次安装、迁移新机器、环境初始化 | 前置条件、API Key 配置、安装流程、launchd 包装脚本、日常运维命令 |
| 2 | [PROJECT_MANUAL.md](docs/PROJECT_MANUAL.md) | 技术参考手册 | 开发、维护、二次改造 | 架构图、模块边界、配置矩阵、索引/搜索流程、调优与部署实践 |
| 3 | [UI_DESIGN_APPLE_GOOGLE.md](docs/UI_DESIGN_APPLE_GOOGLE.md) | Web UI 设计说明 | 界面维护、HIG/Material 对齐、无障碍与动效约定 | 设计原则与设计令牌；中英文页面顶部互链 |
| 4 | [NL_SEARCH_AND_WEB_UI.md](docs/NL_SEARCH_AND_WEB_UI.md) | NL 搜索行为说明 | 智能搜索联调、默认回退路径、接口行为核对 | 意图接口、解读接口、`exact_focus`、限流、无 Key 回退 |


## 技术参考手册范围

[PROJECT_MANUAL.md](docs/PROJECT_MANUAL.md) 是项目的核心技术手册，重点覆盖：


| 范围   | 重点内容                                                        |
| ---- | ----------------------------------------------------------- |
| 基础认知 | 项目目标、核心能力、整体架构                                              |
| 系统设计 | 架构图、技术栈、仓库结构                                                |
| 模块内部 | `app`、`search`、`indexer`、`incremental`、`embedding_cache` 职责 |
| 运行机制 | 配置项矩阵、索引/搜索生命周期、API 能力面                                     |
| 运维实践 | launchd 常驻模型、日常命令、调优策略、从零部署清单                               |


英文文档可通过本页顶部语言链接切换。

## 许可证

本项目采用 [MIT License](LICENSE)。
