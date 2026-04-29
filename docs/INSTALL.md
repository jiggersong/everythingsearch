# EverythingSearch 安装与配置指引

[English](INSTALL.en.md) | [中文](INSTALL.md)

## 概述

本文档说明如何在一台全新的 macOS 机器上安装 EverythingSearch，并在日常环境中运行它。EverythingSearch 会索引本地文件，可选索引 MWeb 导出内容，并通过浏览器在 `http://127.0.0.1:8000` 提供搜索界面。

## 系统要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | macOS 10.15 或更新版本 |
| 磁盘空间 | 至少 500MB |
| 网络 | 安装和索引构建需要联网；浏览器智能搜索与智能解读也需要访问 DashScope；若向量已存在，仅使用 `GET /api/search` 时可不再发起外网请求 |
| Python | 3.10 或 3.11 |
| 外部账号 | DashScope API Key |
| 可选软件 | MWeb，仅在需要索引 MWeb 来源时使用 |

## 一、获取 API Key

1. 打开 [DashScope Console](https://dashscope.console.aliyun.com)。
2. 使用阿里云账号登录。
3. 创建新的 API Key。
4. 保存生成的 Key，例如 `sk-...`。

## 二、自动安装

```bash
cd /path/to/EverythingSearch
./scripts/install.sh
```

安装脚本可以：

1. 检查或安装 Homebrew 与 Python。
2. 创建虚拟环境并安装依赖。
3. 交互式配置 API Key、索引目录和可选的 MWeb 选项。
4. 可选安装 launchd 常驻服务。
5. 可选启动首次全量索引。

## 三、手动安装

### 3.1 创建虚拟环境

```bash
cd /path/to/EverythingSearch
python3.11 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

如果只部署运行时环境，可改用：

```bash
./venv/bin/pip install -r requirements/base.txt
```

### 3.2 配置 API Key 与本地参数

如果 `config.py` 还不存在：

```bash
cp etc/config.example.py config.py
```

推荐优先通过环境变量提供 API Key：

```bash
export DASHSCOPE_API_KEY="sk-你的真实密钥"
```

然后确认 `config.py` 中的主要本地配置：

```python
MY_API_KEY = ""
TARGET_DIR = "/Users/你的用户名/Documents/你的文件夹"

# 仅当 ENABLE_MWEB = True 时需要
# MWEB_LIBRARY_PATH = "..."
# MWEB_DIR = "..."
```

配置优先级：

- 环境变量优先于 `config.py`
- `config.py` 当前仍作为兼容层保留
- `DASHSCOPE_API_KEY`、`MY_API_KEY`、`TARGET_DIR` 不再提供可运行的占位默认值
- 若未显式配置 `PERSIST_DIRECTORY`、`INDEX_STATE_DB`、`SCAN_CACHE_PATH`、`EMBEDDING_CACHE_PATH`，它们默认落在仓库 `data/` 目录下

### 3.3 构建首次索引

```bash
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full
```

### 3.4 启动搜索服务

前台开发模式：

```bash
./venv/bin/python -m everythingsearch.app
# 或
./scripts/run_app.sh dev
```

后台服务模式：

```bash
./scripts/run_app.sh start
./scripts/run_app.sh status
./scripts/run_app.sh restart
./scripts/run_app.sh stop
```

然后打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

### 3.5 可选：使用本地域名

如果你希望使用更容易记住的本地域名，例如 `everythingsearch.local`，可以在 `/etc/hosts` 中添加：

```bash
sudo nano /etc/hosts
```

追加：

```text
127.0.0.1   everythingsearch.local
```

之后访问 [http://everythingsearch.local:8000](http://everythingsearch.local:8000)。

## 四、配置说明

完整配置矩阵请参阅 [PROJECT_MANUAL.md](PROJECT_MANUAL.md)。这里列出最常用的配置项。

### 必填配置

| 配置项 | 说明 |
| --- | --- |
| `TARGET_DIR` | 要索引的根目录，支持单目录或目录列表 |
| `DASHSCOPE_API_KEY` 或 `MY_API_KEY` | 索引生成向量时必须可用；浏览器智能搜索也依赖该密钥 |

### 常用可选配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `ENABLE_MWEB` | `False` | 是否启用 MWeb 导出与索引 |
| `MWEB_LIBRARY_PATH` | macOS 默认路径 | 仅在 MWeb 安装位置非标准时覆盖 |
| `MWEB_DIR` | `data/mweb_export` | MWeb 导出落地区 |
| `SPARSE_TOP_K` | `120` | SQLite FTS5 稀疏检索候选数量 |
| `DENSE_TOP_K` | `120` | 向量库稠密检索候选数量 |
| `FUSION_TOP_K` | `200` | RRF 融合排序后的候选数量 |
| `RERANK_MODEL` | `gte-rerank` | 精排模型（依赖 DashScope，如 `qwen3-rerank`、`gte-rerank`） |
| `CHUNK_SIZE` | `500` | 索引切分块大小 |
| `MAX_CONTENT_LENGTH` | `20000` | 单文件最大索引字符数 |
| `NL_INTENT_MODEL` | `qwen-turbo` | `POST /api/search/nl` 使用的意图模型 |
| `SEARCH_INTERPRET_MODEL` | `qwen-turbo` | 智能解读模型 |
| `RATE_LIMIT_NL_PER_MIN` | `10` | NL 搜索接口每 IP 限流 |
| `RATE_LIMIT_INTERPRET_PER_MIN` | `10` | 解读接口每 IP 限流 |
| `TRUST_PROXY` | `False` | 仅在受控反向代理后面时才信任 `X-Forwarded-For` |

## 五、launchd 与定时增量索引

推荐使用以下脚本安装 launchd wrapper 与 plist：

```bash
./scripts/install_launchd_wrappers.sh
```

这个脚本会：

- 生成 `~/.local/bin/everythingsearch_start.sh`
- 生成 `~/.local/bin/everythingsearch_index.sh`
- 写入 `~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist`
- 写入 `~/Library/LaunchAgents/com.jigger.everythingsearch.plist`

调度行为：

- 搜索服务使用 `RunAtLoad + KeepAlive`
- 定时索引使用 `RunAtLoad + StartInterval`
- 默认间隔是 `1800` 秒，即约每 30 分钟执行一次

仓库中的 [`scripts/launchd/`](../scripts/launchd/) 仅提供参考模板；真正运行时使用的是写入 `~/Library/LaunchAgents/` 的生成文件。

macOS TCC 注意事项：

- LaunchAgent 不应直接指向 `~/Documents` 等受保护目录下的脚本或日志路径
- `~/.local/bin/` 下的 wrapper 脚本可以绕过这一限制，并在脚本内部再 `cd` 到仓库目录

### ⚠️ 完全磁盘访问授权（必读）

安装 launchd 服务后，**必须**授予 Python 和 bash 完全磁盘访问权限，否则每次定时索引执行时 macOS 都会弹出权限确认框，必须手动点击才能继续。

**首先确认 Python 解释器的真实路径：**

```bash
cd /path/to/EverythingSearch
./venv/bin/python -c 'import sys; print(sys.executable)'
```

**然后在系统设置中授权：**

1. 打开 **系统设置 → 隐私与安全性 → 完全磁盘访问**
2. 点击左下角「**＋**」按钮
3. 按 `Cmd+Shift+G`，粘贴上一步输出的 Python 完整路径，点击「打开」
4. 再次点击「**＋**」，同样方式添加 `/bin/bash`（launchd 通过 bash 调用 wrapper 脚本）
5. 确保两个条目的开关均处于「**开启**」状态

也可通过终端直接打开该面板：

```bash
open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
```

> **注意**：Homebrew 升级 Python 小版本时（如 `3.11.15` → `3.11.16`），安装路径中的版本号会变化，需重新授权。运行上述 `python -c` 命令可随时查看最新路径。

## 六、日常使用

### Make 快捷命令

```bash
make help
make index
make index-full
make search q="你要搜索的词"
make app
make app-status
make app-restart
make app-stop
```

`make index` 与 `make index-full` 会在开始前输出文件规模、预计索引块、预计 Token 和预计耗时；运行中每 30 秒输出一次进度，完成后输出总结报告。Token 为本地估算值，实际账单以模型服务商为准。

### 手动增量索引

```bash
./venv/bin/python -m everythingsearch.incremental
./scripts/run_app.sh restart
```

增量索引会先显示新增、修改、删除数量以及预计成本；如果当前向量 collection 缺失，会明确提示并切换到全量重建。

### 全量重建

```bash
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full
./scripts/run_app.sh restart
```

## 七、常见问题

- **搜索不到明明存在的文件**：先确认后缀受支持、文件位于 `TARGET_DIR` 下，再重新执行增量索引。
- **安装时报 `error: externally-managed-environment`**：请使用项目虚拟环境中的 pip，而不是系统 pip。
- **launchd 启动持续失败**：重新执行 `./scripts/install_launchd_wrappers.sh`，并确认生成的 wrapper 路径存在。
- **这台机器没有 DashScope Key**：索引无法生成向量，浏览器智能搜索会关闭；首页会退回到仅调用 `GET /api/search` 的模式。

## 八、文件清单

| 文件或路径 | 用途 |
| --- | --- |
| `scripts/install.sh` | 交互式安装脚本 |
| `scripts/upgrade.sh` | 自动版本升级脚本（v1.0+ → 最新版） |
| `scripts/install_launchd_wrappers.sh` | 生成 launchd wrapper 和 plist |
| `scripts/run_app.sh` | 搜索服务生命周期管理 |
| `docs/PROJECT_MANUAL.md` | 技术手册 |
| `docs/NL_SEARCH_AND_WEB_UI.md` | NL 搜索行为说明 |
| `etc/config.example.py` | 配置模板 |
| `everythingsearch/app.py` | Flask 入口与路由注册 |
| `everythingsearch/retrieval/` | ★ 核心多路检索管道（query_planner / sparse / dense / fusion / reranking / aggregation） |
| `everythingsearch/indexing/` | 双写索引组件（FTS5 稀疏 + ChromaDB 稠密） |
| `everythingsearch/services/` | 服务层 |
| `everythingsearch/request_validation.py` | 请求解析与输入校验 |
| `everythingsearch/infra/` | 设置、限流、日志相关基础设施 |
| `scripts/launchd/*.plist` | launchd 参考模板 |
| `~/.local/bin/everythingsearch_start.sh` | 生成后的应用启动 wrapper |
| `~/.local/bin/everythingsearch_index.sh` | 生成后的增量索引 wrapper |

版本与变更记录见 [GitHub Releases](https://github.com/jiggersong/everythingsearch/releases)。

## 九、版本升级

> ⚠️ **升级前请注意**：升级脚本仅自动迁移 `MY_API_KEY`、`TARGET_DIR`、`ENABLE_MWEB`、`MWEB_LIBRARY_PATH`、`MWEB_DIR` 这 5 个配置项。如果你在旧 `config.py` 中自定义过 `INDEX_ONLY_KEYWORDS`、`HOST`、`PORT`、`NL_INTENT_MODEL`、`SEARCH_INTERPRET_MODEL`、`SPARSE_TOP_K`、`DENSE_TOP_K`、`RERANK_MODEL` 等参数，升级后会回到默认值，请**升级前先备份旧 `config.py`**，升级后手动补回。

如果你之前安装过 v1.0.0 之后任一旧版本，本节将手把手带你升级到最新版。整个升级过程由 `scripts/upgrade.sh` 在 macOS 上自动完成，并依赖 `rsync`，**无需手动处理索引文件或数据迁移**。

### 9.1 准备工作：下载新版

**关键：不要把新版直接解压或复制到旧项目目录里覆盖。** 先下载到一个**全新的独立目录**：

```bash
# 方式一：通过 git clone（推荐）
git clone https://github.com/jiggersong/everythingsearch.git ~/Downloads/EverythingSearch-new

# 方式二：从 GitHub Releases 下载 zip 包后解压
# 假设解压到了 ~/Downloads/EverythingSearch-new
```

> **为什么不能直接覆盖？** 旧项目目录里有很多运行时产生的文件（虚拟环境、索引数据、日志、配置文件），直接覆盖可能造成文件冲突或配置丢失。升级脚本会安全地把新版代码同步过去。

### 9.2 执行升级

进入新下载的目录，运行升级脚本：

```bash
cd ~/Downloads/EverythingSearch-new
./scripts/upgrade.sh
```

脚本默认去检测 `~/Documents/code/EverythingSearch`（安装脚本的默认路径）。如果你的旧项目在其他位置，在命令行上指定：

```bash
./scripts/upgrade.sh /你的/旧项目/路径
```

### 9.3 升级过程详解

运行脚本后，你会看到以下交互步骤，每一步都会清楚说明在做什么：

**① 版本检测** — 脚本自动检查旧项目中的文件特征（目录结构、索引格式、配置文件），判定你是从哪个版本升级上来的，并告诉你对应哪种升级场景。

**② 确认部署位置** — 如果检测到旧项目路径与当前目录不同，脚本会询问「是否将新版本部署到旧安装路径并升级」。选 **Y**（默认）即可。

**③ 数据备份** — 脚本自动将以下关键文件备份到项目目录下的 `upgrade_backups_时间戳/`：
- `config.py`（你的个人配置）
- `embedding_cache.db`（嵌入向量缓存，可节省 API 费用）
- `chroma_db/`（旧向量数据库）

这是关键文件备份，不是完整项目快照；不会包含虚拟环境、日志、稀疏索引、扫描缓存或所有 `data/*.db` 文件。

**④ 配置合并** — 脚本从新版配置模板生成新的 `config.py`，并且只自动迁移旧 `config.py` 中的这些指定字段：`MY_API_KEY`、`TARGET_DIR`、`ENABLE_MWEB`、`MWEB_LIBRARY_PATH`、`MWEB_DIR`。其它自定义项，例如 `INDEX_ONLY_KEYWORDS`、`HOST`、`PORT`、`NL_INTENT_MODEL`、`SEARCH_INTERPRET_MODEL`，会回到模板默认值；如果仍需保留，请升级后对照旧 `config.py` 手动补回。

**⑤ 数据清理** — 根据检测到的旧版本，清理不兼容的文件：

| 场景 | 旧版本范围 | 清理操作 |
|------|-----------|----------|
| **A** | v1.0.x – v1.1.x | 删除旧 ChromaDB（元数据格式不兼容 v2.x），清除扫描缓存和索引状态 |
| **B** | v1.2.0 – v1.5.2 | 删除旧 ChromaDB（无 FTS5 稀疏索引），清除扫描缓存和索引状态，保留 embedding 缓存 |
| **C** | v2.0.0+ | 索引格式兼容，仅清除扫描缓存和索引状态（让下次增量索引自动重建） |

完整性检查阶段会确保 `data/` 目录存在。若场景 C 升级成功但向量检索异常，可删除 `data/chroma_db/` 后执行一次全量重建。

**⑥ 更新依赖与后台服务** — 自动运行 `venv/bin/python -m pip install -r requirements/base.txt`（如果现有虚拟环境是 `.venv`，则使用 `.venv/bin/python`），随后运行 `install_launchd_wrappers.sh` 重新生成 launchd 的 wrapper 脚本和 plist 文件，指向当前项目路径。如果之前注册了开机自启和定时索引，无需重新配置。

**⑦ 重建索引** — 场景 A / B 会提示「是否现在开始重建索引」。**推荐选 Y**，脚本会用 `caffeinate -i` 防止系统休眠，在前台跑完全量重建。根据文件数量，可能需要 10 分钟到数小时。场景 C 则只需运行增量索引验证即可。

### 9.4 升级后验证

全量索引重建完成后，验证一切正常：

```bash
cd ~/Documents/code/EverythingSearch   # 或你的项目路径

# 1. 运行增量索引，确认无报错
./venv/bin/python -m everythingsearch.incremental

# 2. 执行一次搜索，看能否返回结果
./venv/bin/python -m everythingsearch search "测试" --json

# 3. 确保 Web 服务正常运行
./scripts/run_app.sh restart
```

在浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)，搜索几个你印象中的文件，确认结果正常。

### 9.5 清理旧文件

升级成功并确认一切正常后，可以清理不需要的文件：

- **新下载的目录**（如 `~/Downloads/EverythingSearch-new`）：已完成使命，**可以直接删除**
- **旧项目目录**（如 `~/Documents/code/EverythingSearch`）：**已经变成最新版了**，继续用它即可
- **备份目录**（项目目录下的 `upgrade_backups_时间戳/`）：确认升级无误后可以删除，释放磁盘空间

### 9.6 常见问题

**Q: 我已经不小心把新版覆盖到旧目录了怎么办？**

没关系。直接在新旧混合的目录里运行 `./scripts/upgrade.sh` 即可。脚本会检测到这是原地升级，跳过代码同步步骤，直接执行配置合并和数据清理。

**Q: 升级失败了怎么恢复？**

备份目录 `upgrade_backups_时间戳/` 里是升级前的关键文件备份，不是完整项目快照。按需将其中的 `config.py` 和数据目录复制回项目根目录，然后配合旧版代码重新部署；必要时重新构建索引。

**Q: 我有多个 TARGET_DIR，配置能正确迁移吗？**

可以。脚本通过 Python 解析旧 `config.py`，无论 `TARGET_DIR` 是单个路径字符串还是路径列表，都能正确提取并写入新配置。

## 版权

© 2026 jiggersong. Licensed under the MIT License.
