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

### 手动增量索引

```bash
./venv/bin/python -m everythingsearch.incremental
./scripts/run_app.sh restart
```

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
| `scripts/install_launchd_wrappers.sh` | 生成 launchd wrapper 和 plist |
| `scripts/run_app.sh` | 搜索服务生命周期管理 |
| `docs/PROJECT_MANUAL.md` | 技术手册 |
| `docs/NL_SEARCH_AND_WEB_UI.md` | NL 搜索行为说明 |
| `etc/config.example.py` | 配置模板 |
| `everythingsearch/app.py` | Flask 入口与路由注册 |
| `everythingsearch/services/` | 服务层 |
| `everythingsearch/request_validation.py` | 请求解析与输入校验 |
| `everythingsearch/infra/` | 设置、限流、日志相关基础设施 |
| `scripts/launchd/*.plist` | launchd 参考模板 |
| `~/.local/bin/everythingsearch_start.sh` | 生成后的应用启动 wrapper |
| `~/.local/bin/everythingsearch_index.sh` | 生成后的增量索引 wrapper |

版本与变更记录见 [GitHub Releases](https://github.com/jiggersong/everythingsearch/releases)。

## 版权

© 2026 jiggersong. Licensed under the MIT License.
