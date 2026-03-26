# EverythingSearch

[English](README.md) | [中文](README.zh-CN.md)

EverythingSearch 是一个运行在 macOS 上的**本地文件语义搜索引擎**，支持自然语言与关键词检索本地文档、代码、资料与笔记。

## 快速开始

```bash
git clone https://github.com/jiggersong/everythingsearch.git
cd everythingsearch
./scripts/install.sh
```

## 常用命令

```bash
make index         # 增量索引
make index-full    # 全量重建
make app           # 前台运行
make app-status    # 查看常驻服务状态
make app-restart   # 重启常驻服务
make app-stop      # 停止常驻服务
```

## 文档矩阵

| 建议顺序 | 文档 | 角色定位 | 适用场景 | 可获得信息 |
|----------|------|----------|----------|------------|
| 1 | `docs/INSTALL.md` | 安装与运维指南 | 首次安装、迁移新机器、环境初始化 | 前置条件、API Key 配置、安装流程、launchd 包装脚本、日常运维命令 |
| 2 | `docs/PROJECT_MANUAL.md` | 技术参考手册 | 开发、维护、二次改造 | 架构图、模块边界、配置矩阵、索引/搜索流程、调优与部署实践 |
| 3 | `docs/CHANGELOG.md` | 版本与兼容性记录 | 升级评估、回归排查、发布核对 | 各版本用户可见变更、Release 链接、升级背景 |

## 技术参考手册范围

`docs/PROJECT_MANUAL.md` 是项目的核心技术手册，重点覆盖：

| 范围 | 重点内容 |
|------|----------|
| 基础认知 | 项目目标、核心能力、整体架构 |
| 系统设计 | 架构图、技术栈、仓库结构 |
| 模块内部 | `app`、`search`、`indexer`、`incremental`、`embedding_cache` 职责 |
| 运行机制 | 配置项矩阵、索引/搜索生命周期、API 能力面 |
| 运维实践 | launchd 常驻模型、日常命令、调优策略、从零部署清单 |

英文文档可通过本页顶部语言链接切换。

## 许可证

MIT License。
