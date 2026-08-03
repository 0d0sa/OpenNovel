# OpenNovel

一个用于编写小说的 Agent：用户提供剧情（plot），Agent 生成小说片段和章节。
A novel-writing agent: the user supplies a plot (剧情), and the agent produces
novel fragments and chapters.

## 核心目标 / Core requirements

- **语言风格一致性 / Language style consistency**：同一部小说的文风保持统一。
- **剧情连贯性 / Plot coherence**：章节之间的事件、人物、伏笔保持一致。

## 当前状态 / Status

Scaffold + 数据模型 + LLM Provider（MVP 第一步、第二步完成）：`models/`（Pydantic v2 + JSON 持久化）、
`llm/`（openai SDK 兼容层）已实现；memory 逻辑、Agent 编排尚未实现。

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
| `OPENNOVEL_LANGUAGE` | zh | 成书语言 |
| `OPENNOVEL_CHAPTER_TARGET_CHARS` | 3000 | 每章目标字数 |
| `OPENNOVEL_MAX_CHAPTERS` | 20 | 最大章节数 |
| `OPENNOVEL_OUTPUT_DIR` | novels | 成书输出目录 |

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
    style_profile.py  语言风格锚点（StyleProfile，服务风格一致性）
    plot_state.py     剧情状态：人物/事件/伏笔（PlotState，服务剧情连贯性）
  agent/
    orchestrator.py   剧情 -> 场景/章节的编排流程（占位）
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
- [ ] style_profile / plot_state 逻辑（提取、更新、一致性检查）
- [ ] 编排流程：剧情 -> 章节大纲 -> 章节正文
