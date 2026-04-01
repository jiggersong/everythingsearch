# EverythingSearch

[English](README.md) | [中文](README.zh-CN.md)

EverythingSearch 是一个运行在 macOS 上的**本地文件语义搜索引擎**，对应 Windows 下的 Everything 软件的能力，支持自然语言与关键词检索本地文档、代码、资料与笔记。

## 核心能力

- **语义搜索**：不局限于关键词精确匹配，能理解自然语言描述（如"去年的营销方案"）并找到相关文档
- **混合索引**：同时索引文件内容和文件名，确保仅靠文件名也能搜到（如图片、视频）
- **内置 MWeb 无缝集成（可选）**：只需一个开关即可一键接管并可搜索 MWeb 的笔记，结果中以标签区分来源；不需要时可通过 `ENABLE_MWEB=False` 完全关闭
- **位置加权**：关键词出现在文件名、标题中的结果会获得更高的排名
- **Embedding 缓存**：已生成过的向量不会重复调用 API；SQLite 使用 WAL 与连接池，旧库自动迁移 `created_at` 列
- **增量索引**：支持每日自动检测文件变更，仅对新增/修改/删除的文件更新索引
- **搜索内存缓存与健康检查**：重复查询可命中短期内存缓存；提供 `/api/health`（严格的状态语义探针）、`POST /api/cache/clear` 等诊断控制
- **健壮的安全边界守卫**：包含深度的请求前置格式断言（`400`响应拦截），以及严密的路径穿透禁止防御；强制锁定只允许操作位于已登记索引边界内的文件读取和跳转
- **隐私与成本平衡**：索引和数据库完全本地化（ChromaDB），仅在生成向量时调用云端 API（阿里通义千问 DashScope）
- **WebUI 搜索界面**：浏览器中搜索，支持来源过滤、排序、分页、关键词高亮、Finder 定位

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

## 文档矩阵

| 序号 | 文档                                                                                                                                           | 角色定位        | 适用场景                          | 可获得信息                                    |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ----------- | ----------------------------- | ---------------------------------------- |
| 1    | [`INSTALL.md`](docs/INSTALL.md)                                                                                                                | 安装与运维指南     | 首次安装、迁移新机器、环境初始化              | 前置条件、API Key 配置、安装流程、launchd 包装脚本、日常运维命令 |
| 2    | [`PROJECT_MANUAL.md`](docs/PROJECT_MANUAL.md)                                                                                                  | 技术参考手册      | 开发、维护、二次改造                    | 架构图、模块边界、配置矩阵、索引/搜索流程、调优与部署实践            |
| 3    | [`UI_DESIGN_APPLE_GOOGLE.md`](docs/UI_DESIGN_APPLE_GOOGLE.md)                                                                                  | Web UI 设计说明 | 界面维护、HIG/Material 对齐、无障碍与动效约定 | 设计原则与设计令牌；中英文页面顶部互链                              |

## 技术参考手册范围

[`PROJECT_MANUAL.md`](docs/PROJECT_MANUAL.md) 是项目的核心技术手册，重点覆盖：

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
