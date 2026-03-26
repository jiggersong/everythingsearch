# EverythingSearch（中文说明）

EverythingSearch 是一个运行在 macOS 上的**本地文件语义搜索引擎**，支持自然语言与关键词检索本地文档、代码、资料与笔记。

## 文档语言

- 英文（默认）: `README.md` / `README.en.md`
- 中文: `README.zh-CN.md`（本文件）

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

## 中文文档

- 安装说明：`docs/INSTALL.md`
- 项目手册：`docs/PROJECT_MANUAL.md`
- 变更记录：`docs/CHANGELOG.md`
