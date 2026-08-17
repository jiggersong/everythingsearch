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

在 `config.py` 中填写主要本地配置：

```python
MY_API_KEY = "sk-你的真实密钥"
TARGET_DIR = "/Users/你的用户名/Documents/你的文件夹"

# 仅当 ENABLE_MWEB = True 时需要
# MWEB_LIBRARY_PATH = "..."
# MWEB_DIR = "..."
```

配置说明：

- 运行时以 `config.py` 为准；未配置项使用代码内安全默认值
- `MY_API_KEY`、`TARGET_DIR` 不再提供可运行的占位默认值
- 若未显式配置 `PERSIST_DIRECTORY`、`INDEX_STATE_DB`、`SCAN_CACHE_PATH`、`EMBEDDING_CACHE_PATH`，它们默认落在仓库 `data/` 目录下

### 3.3 构建首次索引

```bash
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full
```

### 3.4 启动搜索服务

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
| `MY_API_KEY` | 索引生成向量时必须可用；浏览器智能搜索也依赖该密钥 |

### 常用可选配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `ENABLE_MWEB` | `False` | 是否启用 MWeb 导出与索引 |
| `MWEB_LIBRARY_PATH` | macOS 默认路径 | 仅在 MWeb 安装位置非标准时覆盖 |
| `MWEB_DIR` | `data/mweb_export` | MWeb 导出落地区 |
| `SPARSE_TOP_K` | `120` | SQLite FTS5 稀疏检索候选数量 |
| `DENSE_TOP_K` | `120` | 向量库稠密检索候选数量 |
| `FUSION_TOP_K` | `200` | RRF 融合排序后的候选数量 |
| `RERANK_MODEL` | `qwen3-rerank` | 精排模型（依赖 DashScope，如 `qwen3-rerank`、`gte-rerank`） |
| `CHUNK_SIZE` | `500` | 索引切分块大小 |
| `MAX_CONTENT_LENGTH` | `20000` | 单文件最大索引字符数 |
| `NL_INTENT_MODEL` | `qwen3.7-flash` | `POST /api/search/nl` 使用的意图模型（JSON Mode；调用侧关闭思考模式） |
| `SEARCH_INTERPRET_MODEL` | `qwen3.7-flash` | 智能解读模型（调用侧关闭思考模式） |
| `RATE_LIMIT_NL_PER_MIN` | `10` | NL 搜索接口每 IP 限流 |
| `RATE_LIMIT_INTERPRET_PER_MIN` | `10` | 解读接口每 IP 限流 |
| `TRUST_PROXY` | `False` | 仅在受控反向代理后面时才信任 `X-Forwarded-For` |

## 五、launchd 与定时增量索引

推荐使用以下脚本安装 launchd wrapper 与 plist：

```bash
./scripts/install_launchd_wrappers.sh
```

这个脚本会（**多实例**：同一台 Mac 上不同安装目录可同时常驻，互不覆盖 plist）：

- 按安装目录绝对路径的 SHA-256 **前 12 位**生成实例后缀，写入 `scripts/.launchd_instance` 与 `scripts/.launchd_instance.mk`（供 `run_app.sh`、`Makefile` 解析）
- 在**本仓库** `scripts/` 下生成 `launchd_app_wrapper.sh`、`launchd_index_wrapper.sh`（launchd 通过 `/bin/bash` 执行，再 `cd` 到安装目录，避免 plist 直接指向受 TCC 限制的路径）
- 写入 `~/Library/LaunchAgents/com.jigger.everythingsearch.app.<后缀>.plist` 与 `com.jigger.everythingsearch.index.<后缀>.plist`（Label 与文件名一致）

调度行为：

- 搜索服务使用 `RunAtLoad + KeepAlive`
- 定时索引使用 `RunAtLoad + StartInterval`
- 默认间隔是 `1800` 秒，即约每 30 分钟执行一次

仓库中的 [`scripts/launchd/`](../scripts/launchd/) 仅提供**旧版单实例**参考模板；当前推荐以 `install.sh` 或本脚本生成的 plist 为准。

若机器上仍有旧版固定名称的 plist（`com.jigger.everythingsearch.app.plist` / `com.jigger.everythingsearch.plist`），请在确认无依赖后 `launchctl bootout` 并删除，以免与多实例并存时混淆。

macOS TCC 注意事项：

- plist 的 `ProgramArguments` 指向 `/bin/bash` + 仓库内 wrapper；wrapper 再进入安装目录写日志、启动 gunicorn
- 日志与进程工作目录仍在各实例自己的 `APP_DIR/logs` 下

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
python -m everythingsearch search "你要搜索的词" --json
make start
make status
make restart
make stop
```

`make index` 与 `make index-full` 会在开始前输出文件规模、预计索引块、预计 Token 和预计耗时；运行中每 30 秒输出一次进度，完成后输出总结报告。Token 为本地估算值，实际账单以模型服务商为准。

### 手动增量索引

```bash
./venv/bin/python -m everythingsearch.incremental
```

增量索引完成后会**自动重启**搜索服务以加载新数据（若 launchd 未托管且无法自动拉起，按日志提示手动 `./scripts/run_app.sh start`）。

增量索引会先显示新增、修改、删除数量以及预计成本；若当前向量 collection 缺失，会明确提示并切换到全量重建。

### 全量重建

`make index-full`（或 `incremental --full`）用于**从零重建索引**，与当前 `config.py` 及磁盘内容对齐。

> **v2.5.0 起的目标行为**（文档已更新，代码落地前当前进程仍为 v2.4.0 实现）：默认执行**真·全量**——除重建 sparse / chroma / index_state 外，还会**删除** `embedding_cache.db` 与 `scan_cache.db`，避免旧缓存与新版配置不一致导致检索异常。耗时与 Embedding Token 可能高于保留缓存，但结果最可靠。

**推荐流程（普通用户）**

1. （可选）禁用定时增量以免与全量抢锁：`make index-disable`
2. 执行全量（**默认**会自动暂停并在结束后恢复搜索服务；无需手动 `stop` / `restart`）：

```bash
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full
```

启动时会打印**将删除/将保留**的数据文件摘要；Token 为本地估算，账单以 DashScope 为准。

**Embedding 限速**：`text-embedding-v4` 在中国内地与 v1～v3 **共用**配额（RPS 30、TPM 1,200,000 输入 Token、单批 10 条）。项目默认 `EMBED_RATE_RPS_LIMIT=28` 等略低于官方值；Dense 阶段若遇 429 会自动退避重试，多次失败后 exit 1，可用 `--resume --keep-caches` 续跑。详见 [SEARCH_ACCURACY_TECHNICAL_DESIGN.md](SEARCH_ACCURACY_TECHNICAL_DESIGN.md) §9.1。

**高阶参数**（需省时间或 Token 时显式指定）：

| 参数 | 作用 |
|------|------|
| `--keep-embedding-cache` | 保留向量缓存，Dense 阶段少调 API |
| `--keep-scan-cache` | 保留解析缓存，未变文件跳过重解析 |
| `--keep-caches` | 同时保留上述两项 |
| `--resume` | 中断后续跑（**强制保留**两类 cache 与 checkpoint；不可与「从零 wipe」混用） |
| `--dry-run` | 仅预览将触及的文件，不删除、不写入 |

示例：

```bash
# 中断后续跑（省解析 + 省 Embedding）
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full --resume --keep-caches

# 只保留向量缓存，文件仍全量重解析
caffeinate -i ./venv/bin/python -m everythingsearch.incremental --full --keep-embedding-cache
```

**注意**

- 修改 `EMBEDDING_MODEL`、`EMBEDDING_DIMENSIONS`、`CHUNK_SIZE` 等后，应使用**默认**全量（不 `--keep-*`），或确认你清楚旧 cache 可能部分失效。  
- `--resume` 在 checkpoint 与当前配置指纹不匹配时会失败，需去掉 `--resume` 重新做干净全量。  
- Dense 阶段因 Embedding API 多次重试仍失败时，进程 exit 1；checkpoint 保留，常用 `make index-full ARGS="--resume --keep-caches"` 续跑。  
- 若已有索引任务在跑（含 launchd 定时增量），新的全量会拒绝启动；增量任务冲突时会跳过本次运行。  
- 详见 [PROJECT_MANUAL.md](PROJECT_MANUAL.md) §4.4、§4.4.2 与 §6。

## 七、常见问题

- **搜索不到某个文件**：按下面顺序排查，多数情况是「索引里根本没有这条记录」，而不是检索算法漏掉。
  1. **磁盘上是否还存在**：在 Finder 或终端确认文件路径；若目录已移动、重命名或删除，搜索不会命中。
  2. **是否在 `TARGET_DIR` 范围内**：只有配置目录（及已开启的 MWeb 导出目录）内的文件会被扫描；多实例部署时确认你访问的 Web 端口对应那份安装的 `config.py`。
  3. **索引是否收录**：在**当前运行实例**的数据目录检查：
     ```bash
     # 稀疏索引（文件名 / 正文关键字）
     sqlite3 data/sparse_index.db \
       "SELECT filepath, filename FROM sparse_chunks WHERE filename LIKE '%关键词%' LIMIT 20;"

     # 增量状态表
     sqlite3 index_state.db \
       "SELECT filepath, mtime FROM file_index WHERE filepath LIKE '%关键词%' LIMIT 20;"
     ```
     两条查询均为 0 行 → 该文件从未被当前实例索引，需把文件放回 `TARGET_DIR` 后执行 `make index` 或增量索引。
  4. **后缀与过滤条件**：确认扩展名在支持列表内；Web 若勾选了路径过滤、日期范围或「仅文件名」，会缩小命中范围。
  5. **完整文件名带扩展名仍搜不到（v2.3.4 及更早）**：旧版会把 `.` 当作 FTS 必命中 token，输入 `报告.pdf` 这类完整文件名可能 0 结果；升级到 v2.3.5+ 或改用不含扩展名的关键词搜索。
  6. **同一文件在结果里出现两次（v2.3.4 及更早）**：多见于自 v1.x 升级、Chroma 中 `file_id` 不稳定的旧数据；v2.3.5+ 已按物理路径去重，全量重建索引可彻底对齐 `file_id`。
- **安装时报 `error: externally-managed-environment`**：请使用项目虚拟环境中的 pip，而不是系统 pip。
- **launchd 启动持续失败**：重新执行 `./scripts/install_launchd_wrappers.sh`，并确认生成的 wrapper 路径存在。
- **这台机器没有 DashScope Key**：索引无法生成向量，浏览器智能搜索会关闭；首页会退回到仅调用 `GET /api/search` 的模式。

## 八、文件清单

| 文件或路径 | 用途 |
| --- | --- |
| `scripts/install.sh` | 交互式安装脚本 |
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
| `scripts/launchd_app_wrapper.sh` | 安装/脚本生成后的应用启动 wrapper（gitignore） |
| `scripts/launchd_index_wrapper.sh` | 安装/脚本生成后的增量索引 wrapper（gitignore） |

版本与变更记录见 [GitHub Releases](https://github.com/jiggersong/everythingsearch/releases)。

## 九、更新已有安装

拉取最新代码后，按需重装依赖、刷新 launchd wrapper，并在索引格式变更时全量重建：

```bash
git pull
./venv/bin/pip install -r requirements/base.txt
./scripts/install_launchd_wrappers.sh   # 脚本或 plist 有变更时
make index-full                         # 索引 schema 变更或检索异常时
./scripts/run_app.sh restart
```

更新前请备份 `config.py`。合并代码不会自动迁移自定义配置项；若 `requirements/base.txt` 或索引管线有 breaking change，以 `docs/CHANGELOG.md` 为准。

## 版权

© 2026 jiggersong. Licensed under the MIT License.
