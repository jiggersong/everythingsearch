# OpenClaw 接入 EverythingSearch 指南

本指南帮助你在 **OpenClaw**（或其他只能执行 Shell、或能访问本机 HTTP 的 Agent）中接入 EverythingSearch 本地检索。

更完整的 HTTP API 说明见仓库内 [`skills/everythingsearch-local/SKILL.md`](../skills/everythingsearch-local/SKILL.md)；**OpenClaw 无交互安装（含定时增量索引）**见 [README.zh-CN.md](../README.zh-CN.md) 的「Agent / OpenClaw 非交互安装」；「搜不到文件」排查见 [安装指南](INSTALL.md) 第七节。

---

## 第一步：确认基础环境

1. 已完成安装且至少跑过一次索引。若由 OpenClaw 自动安装，请按 [README.zh-CN.md](../README.zh-CN.md) 执行（含 `./scripts/install_launchd_wrappers.sh`，约每 30 分钟自动增量索引）；人类用户也可走 [安装指南](INSTALL.md) 交互式 `install.sh`。
2. 在项目目录使用**虚拟环境 Python**（不要直接用系统 `python`）：

```bash
cd /您的/EverythingSearch/安装目录
PY=./venv/bin/python
```

3. **DashScope API Key**（CLI 与 NL 搜索必需）  
   CLI 命令 `search` 会先调用意图识别（与 Web「智能搜索」相同），需在 `config.py` 或环境变量中配置 `DASHSCOPE_API_KEY` / `MY_API_KEY`。未配置时 CLI 会返回 `MISSING_API_KEY` 类错误。

4. **HTTP 服务与定时索引**（若 Agent 能用 `curl`，推荐此路径，见下文「方式 B」）：

```bash
# 若尚未注册 launchd，先执行（无交互，同时注册 Web 服务与约 30 分钟定时增量索引）：
./scripts/install_launchd_wrappers.sh

./scripts/run_app.sh status
make index-svc-status
curl -s http://127.0.0.1:8000/api/health
```

### 自检（任选一种通过即可）

**A. 健康检查（仅验证服务，不验证检索）**

```bash
curl -s http://127.0.0.1:8000/api/health | head -c 200
```

**B. HTTP 直接搜索（短关键词即可，不经过大模型意图层）**

```bash
curl -sG "http://127.0.0.1:8000/api/search" \
  --data-urlencode "q=架构" \
  --data-urlencode "limit=3"
```

应返回 JSON，且 `results` 为数组（可为空，但结构正确即表示检索管线正常）。

**C. CLI 自然语言搜索（需 DashScope Key）**

```bash
$PY -m everythingsearch search "帮我找一下架构相关的文档" --json
```

成功时 `stdout` 为单行 JSON，含 `"results"` 数组；**不要**用单独一个词如 `测试`、`架构` 做自检——意图层可能判为 `out_of_scope` 并以非 0 退出码结束，这不代表服务损坏。

---

## 第二步：选择接入方式

### 方式 A：CLI（OpenClaw 只能跑终端命令时）

**命令格式：**

```bash
cd /您的/EverythingSearch/安装目录
./venv/bin/python -m everythingsearch search "<查询>" --json [--limit N] [--source all|file|mweb]
```

| 参数 | 说明 |
| --- | --- |
| `<查询>` | 双引号包裹；支持自然语言，建议带具体主题/文件名/人名，避免过短单字 |
| `--json` | **必填**，保证 stdout 为可解析 JSON |
| `--limit` | 可选，默认 10，最大 200 |
| `--source` | 可选，`all` / `file` / `mweb`（MWeb 需 `ENABLE_MWEB=True`） |

**成功时的 JSON 形状：**

```json
{
  "query": "归一化后的检索词",
  "results": [
    {
      "filepath": "/绝对/路径/文件.pdf",
      "score": 0.85,
      "snippet": "命中片段预览……",
      "mtime": 1710934301.0
    }
  ]
}
```

- `filepath`：可直接用于读文件、`open`、`reveal`。
- `snippet`：命中内容摘要（来自检索管线的 `preview`/`content`）；若为空，请用 Agent 自带能力读取 `filepath` 全文。

**失败时的 JSON：**

```json
{
  "error": "说明文字",
  "capabilities": ["本地文件关键词与条件检索"]
}
```

常见原因：查询过短被意图层拒绝、未配置 API Key、索引未构建、网络无法访问 DashScope。

---

### 方式 B：HTTP API（OpenClaw 能访问 `localhost` 时，更推荐）

基址默认为 `http://127.0.0.1:8000`（端口见 `config.PORT` 或 `scripts/.launchd_instance`）。

| 场景 | 接口 |
| --- | --- |
| 关键词 / 短句，无需大模型 | `GET /api/search?q=...&limit=30` |
| 整句自然语言 + 精确优先 | `POST /api/search/nl`（需 Key） |
| 对已有结果做短总结 | `POST /api/search/interpret`（需 Key） |
| 读文本预览 | `GET /api/file/read?filepath=...` |

示例：

```bash
BASE=http://127.0.0.1:8000
curl -sG "$BASE/api/search" --data-urlencode "q=预算 excel" --data-urlencode "limit=20"
```

HTTP 结果字段为 `preview`（不是 `snippet`）。完整 curl 示例、限流与降级策略见 [`skills/everythingsearch-local/SKILL.md`](../skills/everythingsearch-local/SKILL.md)。

---

## 第三步：配置 OpenClaw 系统提示词

将下面文本粘贴到 OpenClaw 的 **System Prompt** 或 **Tools** 配置区。若 Agent 支持 HTTP，优先按「方式 B」改写命令为 `curl`；否则使用「方式 A」。

```text
# 工具配置: EverythingSearch 本地检索

## 前置
- 工作目录: /您的/EverythingSearch/安装目录
- Python: ./venv/bin/python
- CLI 搜索依赖 DashScope API Key（config 或环境变量）；无 Key 时勿用 CLI，改用 curl GET /api/search（需先 ./scripts/run_app.sh start）

## 方式 A — CLI（仅当无法发 HTTP 时）
./venv/bin/python -m everythingsearch search "<查询>" --json [--limit 20] [--source all]

要求:
- <查询> 用双引号包裹；写清主题/文件名/人名，避免单独「测试」「架构」等过短词。
- 必须带 --json；只解析 stdout 的 JSON，忽略 stderr。
- 从 results[] 取 filepath、snippet；snippet 为空则读取 filepath。

## 方式 B — HTTP（优先）
curl -sG "http://127.0.0.1:8000/api/search" --data-urlencode "q=<关键词>" --data-urlencode "limit=30"
从 results[] 取 filepath、preview。

## 禁止
索引可用时，禁止用 find / mdfind / locate / glob 遍历磁盘代替 EverythingSearch。

## 工作流
1. 用户问本地文档/代码/资料时，先搜索再回答。
2. 路径以 API/CLI 返回的 filepath 为准；终端乱码不影响路径可用性。
3. 搜不到时：确认文件在 TARGET_DIR、索引已更新；详见项目 docs/INSTALL.md 第七节。
```

---

## 第四步：体验与排错

**可以这样问 OpenClaw：**

- 「帮我找电脑里关于产品架构演进的文档。」
- 「哪个文件里有用户登录的实现？」
- 「精确搜索文件名里带预算的 xlsx。」

**搜不到时：**

1. 文件是否仍在 `TARGET_DIR` 下、索引是否收录（见 [INSTALL.md](INSTALL.md) 第七节 SQL 自检）。
2. CLI 是否因过短查询返回 `out_of_scope`——换更具体的问句，或改用 `GET /api/search`。
3. 完整文件名（如 `报告.pdf`）需 **v2.3.5+**；旧版请升级或去掉扩展名再搜。
4. 同一文件出现两条：旧索引 `file_id` 不一致，v2.3.5+ 已按路径去重，必要时全量重建索引。

**延伸阅读：**

- [`skills/everythingsearch-local/SKILL.md`](../skills/everythingsearch-local/SKILL.md) — Agent 完整 HTTP 手册  
- [`docs/PROJECT_MANUAL.md`](PROJECT_MANUAL.md) §3.2 — CLI 与架构说明  
- [`docs/NL_SEARCH_AND_WEB_UI.md`](NL_SEARCH_AND_WEB_UI.md) — NL 搜索与 Web 行为
