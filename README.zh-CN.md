# EverythingSearch

[English](README.md) | [中文](README.zh-CN.md)

EverythingSearch 是运行在 macOS 上的**本地文件语义搜索引擎**，能力与 Windows 下的 **Everything** 相近：支持用**自然语言或关键词**检索本地文档、代码、资料与笔记。

## 核心能力

- **怎么问都能找到**：支持用自然语言描述需求，也支持只输入几个关键词；对已索引的文件快速给出结果，尽量补上 macOS 自带搜索「经常搜不到、排不对」的短板。
- **文件名与正文一起搜**：不只匹配文件名，标题和正文里的内容同样可以命中；系统会更倾向把文件名、标题里就出现线索的结果排在前面，让你少翻几页。
- **把范围缩小再找**：可按文件夹、修改或创建时间筛选结果，也支持「只看文件名」的快速模式，适合只记得大致路径或时间段的情况。
- **浏览器里顺手用**：在本地网页里完成搜索与浏览，界面清晰、结果区宽敞，并可按需打开智能解读等 AI 辅助（需自行配置可用的模型服务）。
- **装一次、以后以增量为主**：首次建立索引会全盘扫描，时间可能较长；索引任务会先输出文件规模、预计 Token 与耗时，运行中每 30 秒更新进度；之后随文件变更增量更新，日常占用和等待都更可控。
- **数据主要留在本机**：索引与向量默认保存在你的 Mac。只有在建立向量、以及你使用智能搜索或智能解读等联网能力时，才会把必要的文本发给所配置的模型服务；未配置密钥时的行为见 [NL_SEARCH_AND_WEB_UI.md](docs/NL_SEARCH_AND_WEB_UI.md)。
- **MWeb 用户一步接入**：若用 MWeb 管理笔记与 Markdown，在配置里打开开关即可把相关内容一并纳入索引。
- **给 Agent 当超级外脑 (CLI 支持)**：我自己平时也在折腾 OpenClaw 这类大模型智能体，为了让它们能帮我找本地文件，我专门写了个纯净输出 JSON 的 CLI 接口。只要简单配一下，你的 Agent 就能立刻长出一双“本地眼睛”！

---

## 快速开始

```bash
git clone https://github.com/jiggersong/everythingsearch.git
cd everythingsearch
./scripts/install.sh
```

## Agent / OpenClaw 非交互安装

`./scripts/install.sh` 是给人类用户设计的交互式安装脚本。  
如果由 OpenClaw 或其他 Agent 安装，请**不要依赖交互输入**，改用下面这套无交互流程：

```bash
git clone https://github.com/jiggersong/everythingsearch.git
cd everythingsearch

# 1) 创建虚拟环境并安装依赖
python3.11 -m venv venv || python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements/base.txt

# 2) 准备 config.py
cp -n etc/config.example.py config.py

# 3) 编辑 config.py（必填：MY_API_KEY、TARGET_DIR）
# 示例：
#   MY_API_KEY = "sk-xxxx"
#   TARGET_DIR = "/Users/你/Documents"

# 4) 首次构建索引
make index

# 5) 注册后台 Web 服务 + 定时增量索引（约每 30 分钟，无需交互确认）
./scripts/install_launchd_wrappers.sh

# 6) 验证（install_launchd_wrappers 会通过 launchctl bootstrap 自动拉起任务）
./scripts/run_app.sh status
make index-status
curl -s http://127.0.0.1:8000/api/health
```

### 后台服务与定时索引（推荐）

`./scripts/install_launchd_wrappers.sh` 会**无交互**完成：

- 按当前安装目录生成唯一 launchd Label（多实例互不冲突）
- 写入 `~/Library/LaunchAgents/` 并 `launchctl bootstrap` 注册两项任务：
  - **搜索 Web 服务**：登录后常驻（`RunAtLoad` + `KeepAlive`）
  - **定时增量索引**：默认每 **30 分钟** 执行一次 `everythingsearch.incremental`（`StartInterval=1800`）

这与 `install.sh` 里可选的 launchd 步骤等价，但**不需要**终端问答；也**不需要**用户在「系统设置」里为定时任务单独点授权（launchd 注册本身可脚本完成）。

调整索引间隔（可选，默认 30 分钟）：

```bash
make index-interval MIN=30
```

### 给 Agent 的执行约束

- 除非 Agent 具备稳定的交互终端能力，否则不要调用 `./scripts/install.sh`。
- 统一使用 `./venv/bin/python` 与 `./venv/bin/pip`，避免系统 Python 歧义。
- Agent 命令中的路径尽量使用绝对路径。
- `TARGET_DIR` 配错会导致索引看似成功但无有效数据，写入前先确认目录存在。
- **不要跳过** `./scripts/install_launchd_wrappers.sh`；否则 `./scripts/run_app.sh start` 会因未注册 launchd 而失败，且磁盘变更不会自动增量索引。
- **`TARGET_DIR` 为 `~/Documents` 等常规目录时**，一般**不必**配置「完全磁盘访问」；仅在启用 MWeb（`ENABLE_MWEB`）或索引 `~/Library` 等受保护路径时，才需按 [INSTALL.md](docs/INSTALL.md) 引导用户到系统设置中手动授权（Agent 无法代点）。
- 如果 Agent 能访问本机 HTTP，请优先按 [`skills/everythingsearch-local/SKILL.md`](skills/everythingsearch-local/SKILL.md) 接入，并优先使用 `GET /api/search` 做稳定检索。

## 更新已有安装

拉取最新代码；若 `requirements/base.txt` 有变更则重装依赖；脚本变更后刷新 launchd wrapper；索引格式变更时执行全量重建：

```bash
git pull
./venv/bin/pip install -r requirements/base.txt
./scripts/install_launchd_wrappers.sh
make index-full
```

## 常用命令

```bash
make help          # 列出全部 make 目标及一行说明
make index         # 增量索引（含规模/Token 预估与 30 秒进度）
make index-full    # 全量重建索引（含规模/Token 预估与 30 秒进度）
make start               # 启动常驻搜索服务
```

**全量重建（v2.5.0 目标行为）**：`make index-full` 默认**真·全量**——重建 sparse/chroma 并**删除** embedding 与 scan 缓存，保证与当前配置一致；启动前会打印将删除/保留的文件摘要。需省 Token 或解析时间时使用 `--keep-embedding-cache`、`--keep-scan-cache` 或 `--keep-caches`；中断续跑用 `--resume --keep-caches`（续跑强制保留两类缓存）。详见 [INSTALL.md](docs/INSTALL.md) 第六节。

```bash
make status            # 查看 launchd 托管服务状态
make restart           # 重启常驻服务
make stop              # 停止常驻服务

# 或者直接用 CLI 模块
python -m everythingsearch search "你要搜的东西" --json
```

## 系统权限与自动化

安装完成后，建议完成以下三项系统级配置，便于服务在后台稳定、免打扰运行：


| 功能         | 说明                                                  |
| ---------- | --------------------------------------------------- |
| **开机自动启动** | 搜索服务（Web UI）在登录后由 launchd 自动拉起，无需手动启动。              |
| **定时更新索引** | 默认每 30 分钟执行增量索引，保持索引与磁盘接近同步。                        |
| **完全磁盘访问** | 为 Python 授予受保护目录（如部分 MWeb 数据路径）的访问权限，避免每次运行都弹出授权提示。 |


> 详细步骤见 [PROJECT_MANUAL.md](docs/PROJECT_MANUAL.md) 第 6.5 节「系统权限与自动化设置」。

## 文档矩阵


| 序号  | 文档                                                                               | 角色              | 适用场景                                  | 可获得信息                                                   |
| --- | -------------------------------------------------------------------------------- | --------------- | ------------------------------------- | ------------------------------------------------------- |
| 1   | [INSTALL.md](docs/INSTALL.md)                                                    | 安装与运维指南         | 首次安装、换新机、环境初始化                        | 前置条件、API Key、安装流程、launchd 包装脚本、日常命令                     |
| 2   | [PROJECT_MANUAL.md](docs/PROJECT_MANUAL.md)                                      | 技术参考手册          | 开发、维护、二次改造                            | 架构、模块边界、配置矩阵、索引/搜索流程、调优与部署                              |
| 3   | [UI_DESIGN_APPLE_GOOGLE.md](docs/UI_DESIGN_APPLE_GOOGLE.md)                      | Web UI 设计说明     | 界面维护、HIG/Material 对齐、无障碍与动效           | 设计原则与设计令牌；中英文页顶互链                                       |
| 4   | [NL_SEARCH_AND_WEB_UI.md](docs/NL_SEARCH_AND_WEB_UI.md)                          | NL 搜索行为说明       | 智能搜索联调、默认回退、接口核对                      | 意图接口、解读接口、`exact_focus`、限流、无 Key 时的行为                   |
| 5   | [SEARCH_ACCURACY_TECHNICAL_DESIGN.md](docs/SEARCH_ACCURACY_TECHNICAL_DESIGN.md)  | 准确率技术设计       | 检索架构重建设计评审                          | FTS5、向量召回、RRF、远端 Rerank、文件聚合、Benchmark 规划与实施路径        |
| 6   | [OPENCLAW_INTEGRATION.zh-CN.md](docs/OPENCLAW_INTEGRATION.zh-CN.md)              | Agent 接入指南        | 给 OpenClaw 配置本地搜索能力                        | 傻瓜式的系统提示词配置向导、验证命令，一看就会                                |
| 7   | [skills/everythingsearch-local/SKILL.md](skills/everythingsearch-local/SKILL.md) | Agent Skill（开源） | Cursor / Claude Code 等与本机 HTTP API 集成 | 各搜索与解读接口的调用示例、基址与 `config.py` 端口、安全与回退；与手册 §3.1 配套 |


## Agent Skill（开源）

仓库根目录 `[skills/everythingsearch-local/SKILL.md](skills/everythingsearch-local/SKILL.md)` 描述如何让 **Cursor、Claude Code 等支持 Agent Skills 的工具** 调用本服务的 HTTP API（混合搜索、自然语言检索、智能解读、读文件等）。在 Cursor 中使用时，可将该目录复制或软链到工作区的 `.cursor/skills/everythingsearch-local/`。详细说明见 [PROJECT_MANUAL.md](docs/PROJECT_MANUAL.md) §3.1。

## 技术参考手册范围

[PROJECT_MANUAL.md](docs/PROJECT_MANUAL.md) 是项目的核心技术参考手册，主要覆盖：


| 范围   | 要点                                                           |
| ---- | ------------------------------------------------------------ |
| 基础   | 项目目标、核心能力、总体架构                                               |
| 系统设计 | 架构图、技术栈、仓库目录                                                 |
| 模块   | `app`、`retrieval.pipeline`、`indexer`、`incremental`、`embedding_cache` 等职责 |
| 运行   | 配置矩阵、索引/搜索生命周期、HTTP API 能力、Agent Skill（§3.1）                 |
| 演进   | 准确率优先检索改造的发布版设计入口                                            |
| 运维   | launchd 模型、常用命令、调优、从零部署检查项                                   |


可通过本页顶部链接切换至英文文档。

## 许可证

本项目采用 [MIT 许可证](LICENSE)。
