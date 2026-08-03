# OpenNovel

一个用于编写小说的 Agent：用户提供剧情（plot），Agent 生成小说片段和章节。
A novel-writing agent: the user supplies a plot (剧情), and the agent produces
novel fragments and chapters.

## 核心目标 / Core requirements

- **语言风格一致性 / Language style consistency**：同一部小说的文风保持统一。
- **剧情连贯性 / Plot coherence**：章节之间的事件、人物、伏笔保持一致。

## 当前状态 / Status

## 当前状态 / Status

MVP 完成：`models/`（Pydantic v2 + JSON 持久化）、`llm/`（openai SDK 兼容层）、
`memory/`（风格提取/锚点/检查 + 剧情增量更新/简报/检查）、`agent/`（编排：剧情→章节）全部实现，
已用真实 API 跑通 1 章成书（含章节规划、逐场景写作、检查与状态更新）。

## 使用 / Usage

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
- [ ] 编排流程：剧情 -> 章节大纲 -> 章节正文
