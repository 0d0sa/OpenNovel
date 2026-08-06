# OpenNovel

一个用于编写小说的 Agent：用户提供剧情（plot），Agent 生成小说片段和章节。
A novel-writing agent: the user supplies a plot (剧情), and the agent produces
novel fragments and chapters.

## 核心目标 / Core requirements

- **语言风格一致性 / Language style consistency**：同一部小说的文风保持统一。
- **剧情连贯性 / Plot coherence**：章节之间的事件、人物、伏笔保持一致。

## 当前状态 / Status

MVP 完成：`models/`（Pydantic v2 + JSON 持久化）、`llm/`（openai SDK 兼容层 + 流式输出）、
`memory/`（风格提取/锚点/检查 + 剧情增量更新/简报/检查）、`ui/`（Codex CLI / Claude Code
风格聊天界面）全部实现，已用真实 API 跑通成书。
v2（对话式写作 Agent）已完成：自由输入由 `agent/loop.py` 的 Agent 循环处理——模型自主决定
是**聊天回答**还是调用工具（类比 Claude Code 在对话与写代码之间切换）；`agent/tools/` 提供
基础工具集（读取 / 提取 / 编写 / 修改 / 保存 / 检查），可逐章交互式写作、随时口头修改。
记忆 v2（三层记忆）已完成：L0 常驻简报（待回收伏笔完整注入）+ L1 章节摘要索引 + L2 全文
检索（`search_memory`）；剧情状态合并升级为 LLM 关系标注 + Python 确定性执行（事件去重、
伏笔语义回收）；记忆与正文分离存储（`novels/<title>/memory.json`），旧书自动迁移。

## 使用 / Usage

### 聊天交互模式（推荐）

```bash
uv run opennovel
```

Codex CLI / Claude Code 风格的**全屏聊天界面**：顶部两行状态栏显示当前作品、模型和
`就绪 / 正在生成 / 等待回答` 状态；中间是可滚动会话记录；底部是固定、可增长的输入区。
界面采用暖橙品牌色与冷灰终端配色，用 `> / * / -` 区分用户、OpenNovel 和进度消息，
在 Windows 与非 TTY 回退终端中也可稳定显示。

Enter 提交，Alt+Enter 换行，输入 `/` 会在输入栏正上方显示命令补全；首项默认选中但不会
改写输入内容，按 Enter 直接执行选中项。PageUp/PageDown 浏览记录。自由输入由
v2 对话式 Agent 处理：闲聊/讨论剧情直接文本回答；写作/修改/查看等请求由模型自主决策并
调用工具（如“把第二章重写得更紧张”触发重写工具），章节正文在会话区流式输出；生成期间
输入自动锁定，但 `/new` 等流程等待用户回答时会恢复输入。非 TTY 环境自动回退到控制台 REPL。

| 命令 | 说明 |
|---|---|
| `/new` | 开始新书：书名 / 剧情（或 `--plot-file`）/ 风格 |
| `/write [N]` | 连续写作 N 章（默认 1，实时进度 + 正文流式输出） |
| `/status` | 章节/字数/检查分数/剧情状态概览 |
| `/style` | 查看当前风格锚点 |
| `/checks` | 查看各章风格与剧情检查报告 |
| `/rewrite N` | 手动重写第 N 章 |
| `/setting` | 打开独立配置页（模型 + 生成参数）；也支持参数式设置、`--list` 和 `--remove NAME` |
| `/model` | 切换已配置的模型（名称或序号） |
| `/sessions` | 当前书的会话列表（名称/消息数/时间） |
| `/session` | 会话管理：`new` / `open` / `rename` / `delete` |
| `/help` `/exit` | 帮助 / 退出 |

### 会话（Session）

一本小说可对应**多个会话**，同一本书的所有会话共享同一份小说背景知识
（剧情 / 风格锚点 / 剧情状态 / 章节，即 novel.json）；每个会话独立保存自己的聊天记录
（`novels/<title>/sessions/<id>.json`），重启后可恢复：

```bash
/sessions                 # 查看本书所有会话
/session new 讨论         # 新建会话（/new 建书时自动创建首个会话）
/session open 讨论        # 切换会话（名称或序号），自动加载共享背景与聊天记录
/session rename 旧名 新名
/session delete 名字
```

多会话同时写作采用写前 reload 的乐观并发（后写覆盖）。全屏顶部状态栏显示当前会话名。

自由输入（自然语言）示例：`帮我开一本新书叫《雾中城》`、`把第二章重写得更紧张`、
`现在写到哪了`、`陈默后来叛变了`（Agent 会调用工具追加剧情）、`写第三第四两章吧`、
`开头改成从雨夜开始，其余不要动`（触发定点修改）。Agent 信息不足时会主动提问澄清
（书名、风格、主角等），也可以纯聊天讨论剧情设定而不动笔。

### Agent 配置

`/setting` 是 Agent 的**唯一配置入口**。模型 profile 和全局生成参数统一保存在
`~/.config/opennovel/settings.json`（原子写入、权限 0600、密钥掩码显示）：

```bash
/setting --name deepseek --base-url https://api.deepseek.com/v1 --api-key sk-xxx --model deepseek-chat
/setting --temperature 0.7 --max-tokens 4096 --interval 20
/setting --list          # 查看所有配置（密钥掩码）
/model qwen              # 按名称切换
/model 2                 # 或按序号切换
```

程序不加载 `.env`，也不读取 `OPENNOVEL_*` 或 `OPENAI_API_KEY`。会话内保存和切换会即时生效并持久化。
首次启动即使尚未配置 API key/model 也会进入交互界面，输入 `/setting` 按提示配置；
API key 输入过程及聊天记录均会隐藏。向导中的 base URL 可直接回车留空（使用 OpenAI 官方地址）。

全屏模式下，裸 `/setting` 会切换到双栏独立配置页。使用 Tab / Shift+Tab 切换字段，Enter 前进
（在最后一项保存），Ctrl+S 随时保存，Esc 返回聊天。控制台回退模式继续使用逐项向导。

### 批量模式

```bash
uv run opennovel write --title 雾中城 --plot "少年雨夜进城寻找失踪的妹妹" --style "冷峻克制"
# 或从文件读剧情：
uv run opennovel write --title 雾中城 --plot-file plot.txt
```

产出 `novels/<title>/novel.json`（全书数据）与 `novels/<title>/novel.txt`（纯文本）。
每章约 7 次 LLM 调用（风格提取 1 + 大纲 1 + 场景 1 + 正文 N + 检查 2 + 状态更新 1）；
rpm 配额低的服务商请在 `/setting` 中增加“调用间隔”。

## LLM 配置 / LLM config

全部配置只从 `/setting` 生成的 `~/.config/opennovel/settings.json` 读取；未配置模型时会话会提示先用
`/setting`。旧 `.env` 中的任何模型或生成参数都不会再注入程序。

全局生成参数：

| 设置项 | 默认 | 说明 |
|---|---|---|
| 采样温度 | 0.7 | 规划大纲调低更稳定，写正文调高更丰富 |
| 单次最大 token | 4096 | 推理模型需为思考过程预留余量 |
| 调用间隔 | 0 秒 | 低 rpm 配额的服务商可设大些 |
| 成书语言 | zh | 小说输出语言 |
| 每章目标字数 | 3000 | 编排器分配场景篇幅的依据 |
| 最大章节数 | 20 | 大纲章节上限 |
| 输出目录 | novels | 成书保存位置 |
| 风格检查 | on | 章节级风格一致性检查开关 |
| 剧情检查 | on | 章节级剧情一致性检查开关 |

## 目录结构 / Structure

```
src/opennovel/
  cli.py            CLI 入口（交互模式 + write 批量成书）
  config.py         应用配置：从 /setting 持久化数据构建 Settings
  models/
    novel.py          数据模型：Novel（正文聚合根）/ Chapter / Scene / Character
    memory.py         记忆聚合根 NovelMemory（风格 + 剧情状态 + 章节摘要）
    memory_store.py   memory.json 原子读写 + 旧书迁移
    storage.py        novel.json 持久化（每书一个 novels/<title>/novel.json）
  llm/
    types.py        消息/请求/响应类型（ChatMessage/CompletionRequest/CompletionResponse）
    provider.py     Provider 抽象基类 + OpenAI 兼容实现 + FakeProvider（测试用）
    registry.py     工厂：从 active 模型配置构建 Provider
  memory/
    style_profile.py  风格锚点：提取 / 锚点块 / 偏离检查（服务风格一致性）
    plot_state.py     剧情状态：关系化增量合并 / 章节摘要 / 简报 / 一致性检查
    retrieval.py      L2 全文检索：句子切分 + 子串匹配 + 角色词典（零依赖）
    summary.py        写前简报校验：锚点 + 完整伏笔 + 摘要与 hook 组装
  agent/
    loop.py          v2 Agent 循环：模型自主决策聊天或调用工具（AgentTurn 协议）
    context.py       背景注入：风格锚点 / 伏笔 / 剧情简报 / 摘要索引 / 章节进度 + 历史窗口
    tools/           基础工具集（@tool 注册）：读取 / 提取 / 编写 / 修改 / 保存 / 检查
    orchestrator.py  批量成书：write_novel + 单章单元 write_one_chapter（工具复用）
    planning.py      章节/场景规划与写作/重写/修改的 LLM 调用
  ui/
    app.py            全屏聊天应用：状态栏/会话区/输入区 + 键盘提示 footer，后台工作线程
    chat.py           聊天流：消息/流式正文/卡片 + rich→ANSI 桥接（ChatView）
    input.py          prompt_toolkit 输入：多行/历史/命令补全（共享 UI_STYLE 主题）
    repl.py           控制台 REPL（非 TTY 回退）：/命令 + 自由文本进 Agent 循环
    display.py        rich 渲染：返回 renderable（面板/表格/检查报告）
    theme.py          共享终端视觉规范：配色 + prompt_toolkit 样式
  settings_store.py   用户配置：模型 profile + 全局生成参数（原子写/0600/掩码）
  session_store.py    会话记录：novels/<title>/sessions/<id>.json（聊天记录/时间）
tests/              冒烟测试 + 数据模型测试
```

## 开发 / Development

环境管理使用 [uv](https://docs.astral.sh/uv/)（不要使用系统 Python）：

```bash
uv sync --dev          # 创建 .venv 并安装依赖（含 dev group）
uv run pytest          # 运行测试
uv run opennovel       # 启动全屏聊天 UI
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
- [x] 全屏聊天界面（Codex CLI / Claude Code 风格状态栏、会话区与固定输入区）
- [x] v2 对话式写作 Agent（Agent 循环 + 基础工具集：读取/提取/编写/修改/保存/检查，意图自决）
- [x] 记忆 v2（三层记忆：常驻简报 + 章节摘要索引 + 全文检索；关系化合并；正文与记忆分离）
