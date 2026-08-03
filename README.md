# OpenNovel

一个用于编写小说的 Agent：用户提供剧情（plot），Agent 生成小说片段和章节。
A novel-writing agent: the user supplies a plot (剧情), and the agent produces
novel fragments and chapters.

## 核心目标 / Core requirements

- **语言风格一致性 / Language style consistency**：同一部小说的文风保持统一。
- **剧情连贯性 / Plot coherence**：章节之间的事件、人物、伏笔保持一致。

## 当前状态 / Status

Scaffold + 数据模型（MVP 第一步）：`models/` 已实现（Pydantic v2 + JSON 持久化），
memory 层基础类型已定义；LLM 接入、Agent 编排等尚未实现。

## 目录结构 / Structure

```
src/opennovel/
  cli.py            CLI 入口（write 命令占位）
  models/
    novel.py        数据模型：Novel（聚合根）/ Chapter / Scene / Character
    storage.py      JSON 持久化（每书一个 novels/<title>/novel.json）
  llm/              LLM provider 抽象层（SDK 选型待定）
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
- [ ] LLM provider 接入（选型待定）
- [ ] style_profile / plot_state 逻辑（提取、更新、一致性检查）
- [ ] 编排流程：剧情 -> 章节大纲 -> 章节正文
