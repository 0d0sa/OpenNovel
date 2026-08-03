# OpenNovel

一个用于编写小说的 Agent：用户提供剧情（plot），Agent 生成小说片段和章节。
A novel-writing agent: the user supplies a plot (剧情), and the agent produces
novel fragments and chapters.

## 核心目标 / Core requirements

- **语言风格一致性 / Language style consistency**：同一部小说的文风保持统一。
- **剧情连贯性 / Plot coherence**：章节之间的事件、人物、伏笔保持一致。

## 当前状态 / Status

Scaffold only — 目录骨架和占位模块，尚无真实实现。

## 目录结构 / Structure

```
src/opennovel/
  cli.py            CLI 入口（write 命令占位）
  models/           数据模型：Novel / Chapter / Scene / Character
  llm/              LLM provider 抽象层（SDK 选型待定）
  memory/
    style_profile.py  语言风格锚点（服务风格一致性）
    plot_state.py     剧情状态：人物/事件/伏笔（服务剧情连贯性）
  agent/
    orchestrator.py   剧情 -> 场景/章节的编排流程（占位）
tests/              冒烟测试
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

- [ ] 数据模型（Novel / Chapter / Scene / Character）
- [ ] LLM provider 接入（选型待定）
- [ ] style_profile / plot_state 持久化
- [ ] 编排流程：剧情 -> 章节大纲 -> 章节正文
