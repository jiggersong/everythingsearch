# OpenClaw 接入 EverythingSearch 指南

本指南旨在帮助非技术背景的用户，通过简单的配置让 **OpenClaw**（或其他智能体 Agent）掌握强大的本地文件检索能力。配置完成后，您的 OpenClaw 将能够通过自然语言快速帮您找到电脑上的文档和代码。

## 第一步：确认基础环境

在开始之前，请确保您已经完成了 EverythingSearch 的安装并启动了索引。
如果您还没有安装，请先参考 [安装指南](INSTALL.md) 完成基础安装。

验证方法：打开您的终端 (Terminal)，执行以下命令：
```bash
cd /您的/EverythingSearch/安装目录
python -m everythingsearch search "测试" --json
```
如果能输出一串带有 `"results"` 的文本（即使是空的），说明一切准备就绪！

## 第二步：配置 OpenClaw

OpenClaw 等 Agent 工具通常允许您自定义它的 **系统提示词 (System Prompt)** 或 **工具包 (Tools)**。您只需要将以下文本完整复制并粘贴到 OpenClaw 的设定区域中即可。

### 复制以下设定代码：

```text
# 工具配置: EverythingSearch 本地检索
你现在具备了通过 EverythingSearch 智能搜索用户本地文件的能力。

## 调用命令
`python -m everythingsearch search "<查询词>" --json`

## 参数要求
- `<查询词>`: 必须使用双引号包裹，支持自然语言。例如 "帮我找一下上周写的设计文档"。
- `--limit <数字>`: (可选) 限制结果条数，默认 10 条。
- `--json`: (必填) 必须带上此参数，用于保证你能够解析返回的格式化结果。

## 你的工作流
1. 当用户询问本地的文档、代码、资料或项目信息时，主动调用该命令。
2. 你需要解析终端输出的 JSON 数据，提取出 `filepath` (文件路径) 和 `snippet` (相关片段)。
3. 根据提取到的内容向用户作答，如果需要更深入的了解，请使用你自带的文件读取能力直接读取对应的 `filepath`。
```

## 第三步：体验智能搜索

配置保存后，您就可以直接在 OpenClaw 的聊天框里向它下达任务了！

**您可以这样问它：**
- "帮我找一下电脑里关于『产品架构演进』相关的文档。"
- "我们在哪个文件里实现了用户登录的逻辑？"
- "总结一下我本地所有关于 Nginx 的配置文件信息。"

**背后发生了什么？**
OpenClaw 接收到您的话后，会思考并自动向您的电脑后台发送 `python -m everythingsearch search "查询词" --json` 命令，秒级获取所有相关文档片段，然后把结果整理成一段人话回答您。

---

如果遇到任何搜不到的情况，可以检查您的 EverythingSearch 后台索引是否更新完成。
