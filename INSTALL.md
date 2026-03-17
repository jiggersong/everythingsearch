# EverythingSearch 安装与配置指引

## 概述

本文档指导你在一台全新的 Mac 上安装并配置 EverythingSearch 本地语义搜索引擎。安装完成后，你可以通过浏览器搜索本地文件；如启用 MWeb，也可同时检索 MWeb 导出的 Markdown 笔记。

---

## 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | macOS 10.15 (Catalina) 或更新版本 |
| 磁盘空间 | 至少 500MB 可用空间 |
| 网络 | 安装和索引构建时需要联网，搜索时不需要 |
| Python | 3.10 或 3.11（安装脚本会自动安装） |
| 外部账号 | 阿里云 DashScope API Key（免费注册） |
| 可选软件 | MWeb（仅在需要检索 MWeb 内容时才需要） |

---

## 一、获取 API Key（安装前准备）

1. 访问 https://dashscope.console.aliyun.com
2. 使用阿里云账号登录（没有账号需先注册）
3. 在控制台中选择「API-KEY 管理」→「创建新的 API-KEY」
4. 复制生成的 Key（格式为 `sk-xxxxxxxxxxxxxxxx`），安装时会用到

---

## 二、自动安装（推荐）

### 方式 A：直接运行安装脚本

将整个项目文件夹复制到新电脑后，在终端中执行：

```bash
cd /path/to/EverythingSearch
./install.sh
```

安装脚本会自动完成以下步骤：
1. 检查并安装 Homebrew（如未安装）
2. 检查并安装 Python 3.11（如未安装）
3. 将项目文件复制到目标位置
4. 创建 Python 虚拟环境
5. 安装所有 Python 依赖
6. **交互式配置**：引导你输入 API Key、索引目录，并可选择是否启用 MWeb
7. 创建快捷启动脚本
8. 可选安装每日自动增量索引
9. 可选立即构建首次索引

### 方式 B：打包传输

在原始电脑上打包项目（不含数据库和虚拟环境）：

```bash
cd ~/Documents/code
tar czf EverythingSearch-install.tar.gz \
    --exclude='venv' \
    --exclude='chroma_db' \
    --exclude='embedding_cache.db' \
    --exclude='index_state.db' \
    --exclude='scan_cache.db' \
    --exclude='__pycache__' \
    --exclude='.DS_Store' \
    --exclude='logs/*.log' \
    EverythingSearch/
```

在新电脑上解压并运行安装：

```bash
cd ~/Documents/code
tar xzf EverythingSearch-install.tar.gz
cd EverythingSearch
./install.sh
```

---

## 三、手动安装

如果自动安装脚本遇到问题，按以下步骤手动操作。

### 3.1 安装 Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 3.2 安装 Python 3.11

```bash
brew install python@3.11
```

### 3.3 创建虚拟环境

```bash
cd /path/to/EverythingSearch
python3.11 -m venv venv
```

### 3.4 安装依赖

```bash
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

### 3.5 编辑配置文件

若 `config.py` 不存在，先复制模板：`cp config.example.py config.py`

用文本编辑器打开 `config.py`，修改以下必填项：

```python
# [必填] 阿里云 DashScope API Key
MY_API_KEY = "sk-你的API密钥"

# [必填] 要索引的文件根目录
TARGET_DIR = "/Users/你的用户名/Documents/你的文件夹"

# [可选] MWeb 笔记导出目录（不使用 MWeb 可忽略）
MWEB_DIR = "/Users/你的用户名/Documents/MWebMarkDown/File"
```

### 3.6 构建首次索引

```bash
# 使用 caffeinate 防止电脑休眠中断长时间运行
caffeinate -i ./venv/bin/python incremental.py --full
```

索引时间取决于文件数量和类型：
- 100 个文件：约 2-5 分钟
- 1000 个文件：约 15-30 分钟
- 5000+ 个文件：约 1-3 小时

### 3.7 启动搜索服务

**方式一：开发模式（前台运行）**
```bash
./venv/bin/python app.py
# 或
./run_app.sh dev
```

**方式二：常驻模式（后台运行，支持重启）**
```bash
./run_app.sh start    # 启动
./run_app.sh stop     # 停止
./run_app.sh restart  # 重启
./run_app.sh status   # 查看状态
```

**方式三：开机自启（launchd）**

> **注意**：macOS 对 `~/Documents` 目录有 TCC 隐私保护，LaunchAgent 无法直接访问该路径下的脚本和日志文件。因此 launchd 通过调用 `~/.local/bin/` 下的 wrapper 脚本来启动服务，由脚本内部 `cd` 到项目目录。

```bash
# 1. 创建 wrapper 脚本（launchd 通过它来启动服务）
mkdir -p ~/.local/bin
cp launchd_wrapper.sh ~/.local/bin/everythingsearch_start.sh
chmod +x ~/.local/bin/everythingsearch_start.sh
# 编辑 ~/.local/bin/everythingsearch_start.sh 确认 APP_DIR 路径正确

# 2. 安装 plist（plist 已配置为调用 wrapper 脚本）
cp com.jigger.everythingsearch.app.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.app.plist

# 卸载:
# launchctl bootout gui/$(id -u)/com.jigger.everythingsearch.app
```

浏览器打开 http://127.0.0.1:8000 开始搜索。

### 3.8 使用本地域名访问（可选）

若希望用易记的本地域名（如 `http://everythingsearch.local:8000`）访问，只需让该域名解析到本机：

1. **编辑 hosts 文件**（需要管理员权限）：
   ```bash
   sudo nano /etc/hosts
   ```
2. **在文件末尾添加一行**（域名可自定，如 `ererythingsearch.local` 或 `everythingsearch.local`）：
   ```
   127.0.0.1   everythingsearch.local
   ```
3. 保存退出后，在浏览器中访问：**http://everythingsearch.local:8000** 即可。

无需修改应用代码；请求会经 hosts 解析到 127.0.0.1，服务照常监听 127.0.0.1:8000。若希望不加端口号（仅 `http://everythingsearch.local`），可将 `config.py` 中 `PORT = 80` 并用 `sudo ./venv/bin/python app.py` 启动，或使用 Nginx/Caddy 等反向代理将 80 转发到 8000。

---

## 四、配置说明

所有配置项集中在 `config.py` 文件中。

### 必填配置

| 配置项 | 说明 | 示例 |
|-------|------|------|
| `MY_API_KEY` | DashScope API Key（推荐改为设置环境变量 `DASHSCOPE_API_KEY`，避免写入文件） | `"sk-xxxx..."` |
| `TARGET_DIR` | 要索引的文件根目录 | `"/Users/me/Documents"` |

### 可选配置

| 配置项 | 默认值 | 说明 |
|-------|--------|------|
| `ENABLE_MWEB` | `False` | 是否启用 MWeb 数据源。关闭后会跳过 MWeb 导出/扫描，且搜索页不再显示「MWeb笔记」来源 |
| `MWEB_DIR` | `".../MWebMarkDown/File"` | MWeb 笔记导出目录 |
| `MWEB_EXPORT_SCRIPT` | `".../mweb_export.py"` | MWeb 导出脚本路径 |
| `INDEX_ONLY_KEYWORDS` | `[]` | 只索引路径含特定关键词的文件，空列表=全部索引 |
| `SEARCH_TOP_K` | `250` | 每个来源检索候选数量，越大结果越多但越慢 |
| `SCORE_THRESHOLD` | `0.45` | 相关度阈值，越小越严格 |
| `CHUNK_SIZE` | `500` | 文本切分块大小 |
| `MAX_CONTENT_LENGTH` | `20000` | 单文件最大索引字符数 |

### 搜索调优建议

- **搜索结果太少**：调大 `SCORE_THRESHOLD`（如 0.55）或调大 `SEARCH_TOP_K`
- **搜索结果太杂**：调小 `SCORE_THRESHOLD`（如 0.35）
- **搜索太慢**：调小 `SEARCH_TOP_K`（如 100）

修改配置后需重启搜索服务：`./run_app.sh restart` 或重新运行 `python app.py`。

---

## 五、定时自动增量索引

设置后系统每天自动检测文件变更并更新索引。

### 安装定时任务

> 同搜索服务一样，定时索引也需要通过 `~/.local/bin/` 下的 wrapper 脚本来绕过 TCC 限制。

```bash
# 1. 创建 wrapper 脚本
mkdir -p ~/.local/bin
cp launchd_wrapper.sh ~/.local/bin/everythingsearch_index.sh
# 注意：需将 everythingsearch_index.sh 的内容改为调用 incremental.py
#       （安装脚本 install.sh 会自动生成正确内容）
chmod +x ~/.local/bin/everythingsearch_index.sh

# 2. 安装 plist
cp com.jigger.everythingsearch.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

### 修改执行时间

编辑 `com.jigger.everythingsearch.plist` 中的以下部分：

```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>10</integer>     <!-- 修改为目标小时（24h） -->
    <key>Minute</key>
    <integer>0</integer>      <!-- 修改为目标分钟 -->
</dict>
```

修改后重新加载：

```bash
launchctl bootout gui/$(id -u)/com.jigger.everythingsearch
cp com.jigger.everythingsearch.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

### 检查定时任务状态

```bash
launchctl list | grep everythingsearch
```

### 卸载定时任务

```bash
launchctl bootout gui/$(id -u)/com.jigger.everythingsearch
rm ~/Library/LaunchAgents/com.jigger.everythingsearch.plist
```

### 查看索引日志

```bash
# 标准输出日志
cat logs/incremental.log

# 错误日志
cat logs/incremental_err.log
```

---

## 六、日常使用

### 启动搜索

```bash
cd /path/to/EverythingSearch
# 开发模式（前台）
./run_app.sh dev
# 或: ./venv/bin/python app.py

# 常驻模式（后台，支持重启）
./run_app.sh start
./run_app.sh status   # 查看状态
./run_app.sh restart  # 重启
./run_app.sh stop     # 停止
```

浏览器打开 http://127.0.0.1:8000

### 搜索技巧

- **直接输入关键词**：在搜索框中输入后按 Enter
- **来源过滤**：点击「全部」「文件」「MWeb」按钮切换搜索范围
- **排序切换**：选择按相关度或修改时间排序
- **打开文件位置**：点击搜索结果中的「在 Finder 中显示」

### 手动执行增量索引

当文件有大量变更时，可手动触发：

```bash
./venv/bin/python incremental.py
# 索引完成后需重启搜索服务以加载新数据
./run_app.sh restart
```

### 完整重建索引

更换索引目录或数据异常时使用：

```bash
caffeinate -i ./venv/bin/python incremental.py --full
# 索引完成后需重启搜索服务以加载新数据
./run_app.sh restart
```

---

## 七、常见问题

### Q: 安装依赖时报错 `error: externally-managed-environment`
**A**: 确保使用的是项目的虚拟环境 `./venv/bin/pip`，不要使用系统 Python 的 pip。

### Q: 索引构建时提示 `InvalidParameter: Range of input length should be [1, 2048]`
**A**: 这通常是某个文件内容过长导致的，系统已内置截断机制。如果仍然出现，可适当调小 `config.py` 中的 `CHUNK_SIZE`。

### Q: 索引构建中途电脑休眠导致中断
**A**: 使用 `caffeinate -i` 前缀运行命令，可防止系统休眠。

### Q: 搜索不到已知存在的文件
**A**: 
1. 确认文件后缀在 `config.py` 的 `SUPPORTED_EXTENSIONS` 中
2. 确认文件在 `TARGET_DIR` 目录下
3. 运行 `python incremental.py` 更新索引
4. 重启搜索服务以加载新索引：`./run_app.sh restart`

### Q: launchd 开机自启服务一直失败（退出码 78）
**A**: 这是 macOS TCC 隐私保护导致的。LaunchAgent 无法直接访问 `~/Documents` 目录。解决方法：确保使用 `~/.local/bin/` 下的 wrapper 脚本启动（而非在 plist 中直接引用 `~/Documents` 下的 Python 或脚本），plist 的 `StandardOutPath`/`StandardErrorPath` 也应指向 `/tmp/` 而非 `~/Documents`。运行 `install.sh` 可自动完成正确配置。

### Q: 如何更换 API Key
**A**: 编辑 `config.py` 中的 `MY_API_KEY`，重启搜索服务即可。无需重建索引。

### Q: 这台电脑没有 MWeb，能否完全忽略 MWeb？
**A**: 可以。将 `config.py` 中的 `ENABLE_MWEB = False`，并把 `MWEB_DIR` / `MWEB_EXPORT_SCRIPT` 设为空字符串。之后：
- 增量索引不会再运行 MWeb 导出，也不会扫描 MWeb
- 搜索结果页「来源」中不再显示「MWeb笔记」

### Q: 数据库文件太大
**A**: 
- `embedding_cache.db`：向量缓存，删除后重建索引时会重新调用 API 生成
- `chroma_db/`：向量数据库，只能通过 `--full` 重建清理

---

## 八、文件清单

安装包中包含的文件：

| 文件 | 用途 |
|------|------|
| `install.sh` | 自动安装脚本 |
| `INSTALL.md` | 本安装指引 |
| `PROJECT_MANUAL.md` | 项目详细说明书 |
| `config.py` | 配置文件（需编辑） |
| `config.example.py` | 配置模板 |
| `app.py` | Web 服务入口 |
| `run_app.sh` | 搜索服务管理（start/stop/restart/status/dev） |
| `search.py` | 搜索引擎核心 |
| `indexer.py` | 索引构建程序 |
| `incremental.py` | 增量索引程序 |
| `embedding_cache.py` | 向量缓存层 |
| `requirements.txt` | Python 依赖清单 |
| `templates/index.html` | 搜索页面 |
| `static/icon.png` | 页面图标 |
| `com.jigger.everythingsearch.plist` | 定时索引任务 plist 配置 |
| `com.jigger.everythingsearch.app.plist` | 搜索服务常驻 plist 配置 |
| `~/.local/bin/everythingsearch_start.sh` | 搜索服务 launchd wrapper 脚本（安装时生成） |
| `~/.local/bin/everythingsearch_index.sh` | 增量索引 launchd wrapper 脚本（安装时生成） |

---

## 版权

© 2026 jiggersong. Licensed under the Apache License 2.0.
