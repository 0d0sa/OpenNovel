# OpenNovel

一个用于编写小说的 Agent：用户提供剧情（plot），Agent 生成小说片段和章节。
A novel-writing agent: the user supplies a plot (剧情), and the agent produces
novel fragments and chapters.

## 核心目标 / Core requirements

- **语言风格一致性 / Language style consistency**：同一部小说的文风保持统一。
- **剧情连贯性 / Plot coherence**：章节之间的事件、人物、伏笔保持一致。

## 当前状态 / Status

## 当前状态 / Status

MVP 完成：`models/`（Pydantic v2 + JSON 持久化）、`llm/`（openai SDK 兼容层 + 流式输出）、
`memory/`（风格提取/锚点/检查 + 剧情增量更新/简报/检查）、`agent/`（编排 + 意图路由）、
`ui/`（Claude Code 风格聊天界面）全部实现，已用真实 API 跑通成书。

## 使用 / Usage

### 聊天交互模式（推荐）

```bash
uv run opennovel
```

Claude Code 风格的聊天界面：底部输入框（Enter 提交、Shift+Enter 换行、`/` 命令自动补全、历史浏览），
自然语言直接理解（LLM 意图路由，如"把第二章重写得更紧张"直达重写），正文流式滚动在聊天流中。

| 命令 | 说明 |
|---|---|
| `/new` | 开始新书：书名 / 剧情（或 `--plot-file`）/ 风格 |
| `/write` | 写作当前书（实时进度 + 正文流式输出） |
| `/status` | 章节/字数/检查分数/剧情状态概览 |
| `/style` | 查看当前风格锚点 |
| `/checks` | 查看各章风格与剧情检查报告 |
| `/rewrite N` | 手动重写第 N 章 |
| `/help` `/exit` | 帮助 / 退出 |

自由输入（自然语言）示例：`帮我开一本新书叫《雾中城》`、`把第二章重写得更紧张`、
`现在写到哪了`、`陈默后来叛变了`（=追加剧情）。

### 批量模式

```bash
uv run opennovel write --title 雾中城 --plot "少年雨夜进城寻找失踪的妹妹" --style "冷峻克制"
# 或从文件读剧情：
uv run opennovel write --title 雾中城 --plot-file plot.txt --max-chapters 5
```

产出 `novels/<title>/novel.json`（全书数据）与 `novels/<title>/novel.txt`（纯文本）。
每章约 7 次 LLM 调用（风格提取 1 + 大纲 1 + 场景 1 + 正文 N + 检查 2 + 状态更新 1）；
rpm 配额低的服务商请设置 `OPENNOVEL_LLM_INTERVAL`。

## LLM 配置 / LLM config

Provider 层使用 openai SDK 兼容 OpenAI 兼容服务（DeepSeek / 通义千问 / 智谱 GLM / Moonshot 等），
全部通过环境变量配置（缺 API key 或 model 时命令行会报清晰错误）。
参考 `.env.example`：`cp .env.example .env` 后按服务商填写，CLI 启动时自动加载（python-dotenv）。

主要配置项（前缀 `OPENNOVEL_`）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `OPENNOVEL_LLM_API_KEY` | - | API 密钥（必填，或用 `OPENAI_API_KEY`） |
| `OPENNOVEL_LLM_MODEL` | - | 模型名（必填） |
| `OPENNOVEL_LLM_BASE_URL` | OpenAI 官方 | 服务地址 |
| `OPENNOVEL_LLM_TEMPERATURE` | 0.7 | 采样温度（规划大纲调低更稳定，写正文调高更丰富） |
| `OPENNOVEL_LLM_MAX_TOKENS` | 4096 | 单次调用 token 上限（推理模型需留思考余量） |
| `OPENNOVEL_LLM_INTERVAL` | 0 | 每次调用前固定等待秒数（低 rpm 配额的服务商设大些） |
| `OPENNOVEL_LANGUAGE` | zh | 成书语言 |
| `OPENNOVEL_CHAPTER_TARGET_CHARS` | 3000 | 每章目标字数 |
| `OPENNOVEL_MAX_CHAPTERS` | 20 | 最大章节数 |
| `OPENNOVEL_OUTPUT_DIR` | novels | 成书输出目录 |
| `OPENNOVEL_STYLE_CHECK` | on | 章节级风格一致性检查开关 |
| `OPENNOVEL_PLOT_CHECK` | on | 章节级剧情一致性检查开关 |

## 目录结构 / Structure

```
src/opennovel/
  cli.py            CLI 入口（write 命令占位）
  config.py         应用配置：Settings + load_settings（读 OPENNOVEL_* 环境变量）
  models/
    novel.py        数据模型：Novel（聚合根）/ Chapter / Scene / Character
    storage.py      JSON 持久化（每书一个 novels/<title>/novel.json）
  llm/
    types.py        消息/请求/响应类型（ChatMessage/CompletionRequest/CompletionResponse）
    provider.py     Provider 抽象基类 + OpenAI 兼容实现 + FakeProvider（测试用）
    registry.py     工厂：从环境变量配置 Provider
  memory/
    style_profile.py  风格锚点：提取 / 锚点块 / 偏离检查（服务风格一致性）
    plot_state.py     剧情状态：增量更新 / 简报 / 一致性检查（服务剧情连贯性）
  agent/
    orchestrator.py   write_novel：剧情 -> 大纲 -> 逐场景写作 -> 检查/重写 -> 状态更新
    planning.py       章节/场景规划与写作/重写的 LLM 调用
  ui/
    chat.py           聊天流：消息/流式正文/章节完成卡片
    input.py          prompt_toolkit 输入：多行/历史// 命令补全
    repl.py           聊天会话：/命令 + 意图路由分发
    display.py        rich 渲染：面板/表格/检查报告
  agent/
    intent.py         LLM 意图路由：自然语言 -> 命令
tests/              冒烟测试 + 数据模型测试
```

## 开发 / Development

环境管理使用 [uv](https://docs.astral.sh/uv/)（不要使用系统 Python）：

```bash
uv sync --dev          # 创建 .venv 并安装依赖（含 dev group）
uv run pytest          # 运行测试
uv run opennovel       # 运行 CLI（仅占位）
```

提交 `uv.lock` 以保证依赖可复现；依赖变更后重新运行 `uv sync --dev`。

## 路线图 / Roadmap

- [x] 数据模型（Novel / Chapter / Scene / Character + JSON 持久化）
- [x] LLM provider 接入（openai SDK + OpenAI 兼容服务）
- [x] style_profile 逻辑（前置提取 / 锚点注入 / 章节级检查）
- [x] plot_state 逻辑（增量更新 / 简报注入 / 章节级检查）
- [x] 编排流程：剧情 -> 章节大纲 -> 章节正文（真实 API 验证通过）
- [x] 终端交互界面（rich REPL：/new /write /status /style /checks /rewrite + 流式输出）
- [x] 聊天式界面（prompt_toolkit 输入 + LLM 意图路由，Claude Code 风格）
- [ ] 编排流程：剧情 -> 章节大纲 -> 章节正文
