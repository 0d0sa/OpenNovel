# AGENTS.md

## Project goal

Build an agent that writes novels: the user supplies a plot (剧情), and the agent produces novel scenes/fragments and chapters. Two non-negotiable quality requirements, per novel:

- **Language style consistency** (语言风格一致性): the writing voice/style must stay uniform across the whole novel.
- **Plot coherence** (剧情连贯性): events, characters, and setups must remain consistent across chapters.

Treat these as first-class architectural constraints, not afterthoughts. Any design (prompt scaffolding, memory/state, per-novel context, style anchors) should explicitly serve them.

## Repo state

- Python CLI project: `pyproject.toml` (hatchling, src layout), `src/opennovel/` package, `tests/`. MVP is complete (all 8 steps done) — see the per-step status below.
- Decisions already made: Python, CLI tool, native LLM SDK hand-written orchestration (no agent framework). LLM provider: openai SDK against OpenAI-compatible services (DeepSeek/通义/智谱/etc. via `base_url`). All configuration comes ONLY from `~/.config/opennovel/settings.json`, managed by `/setting`; the application never loads `.env` or reads `OPENNOVEL_*`/`OPENAI_API_KEY`. SDK usage must stay inside `llm/` — never import it in upper layers.
- Data models are done (MVP step 1): Pydantic v2, `Novel` as aggregate root holding `style_profile`/`plot_state`, JSON persistence per book (`novels/<title>/novel.json`). Style memory is done (MVP step 3): one-time upfront extraction + anchor-block injection + chapter-level deviation check (`memory/style_profile.py`), toggled in `/setting`. Plot memory is done (MVP step 4): incremental LLM extraction + deterministic merge, compressed brief injection, chapter-level consistency check (`memory/plot_state.py`), toggled in `/setting`. Orchestration (剧情 -> chapters) is done (MVP step 5): `agent/planning.py` (outline/scenes/writing/rewrite prompts) + `agent/orchestrator.py` (`write_novel`, per-chapter save + novel.txt export), CLI `opennovel write`. Interactive UI is done on branch `frontend` (MVP step 6): rich-based REPL (`ui/repl.py` + `ui/display.py`), streaming output (`Provider.stream_complete`), per-chapter check reports stored on `Chapter.style_report`/`plot_report`. Chat-style UI is done on branch `frontend` (MVP step 7): prompt_toolkit input (`ui/input.py`, multiline/history/`/` completion), chat stream (`ui/chat.py`), LLM intent routing for free text (`agent/intent.py`, fallback to append-plot on failure). Full-screen chat UI is done on branch `frontend` (MVP step 8): `ui/app.py` (prompt_toolkit full-screen Application — 2-line status bar with book/model/state, scrollable transcript with scrollbar + PageUp/PageDown, composer with `> ` prompt and keyboard-hint footer, completions menu; background worker thread; input locked while busy except when a command is awaiting an answer), Codex/Claude-style visual tokens centralized in `ui/theme.py` (shared by prompt_toolkit `UI_STYLE` and rich colors), rich→ANSI bridge (`ChatView`/`render_ansi`), display.py returns renderables, console REPL kept as non-TTY fallback. Runtime configuration is done on branch `fix`: bare `/setting` opens a dedicated full-screen form (console fallback uses a wizard); flags, `--list`, and `--remove` remain available; `/model` switches by name/index. Named profiles and global runtime settings live in `~/.config/opennovel/settings.json` (`settings_store.py`, atomic write, 0600, masked keys), and `Session.switch_provider` rebuilds the provider live. Session management is done on branch `fix`: one novel maps to multiple sessions sharing the whole Novel as background knowledge; `session_store.py` persists chat history per session (`novels/<title>/sessions/<id>.json`), commands `/sessions` + `/session new|open|rename|delete` (first session auto-created on `/new`, chat restored on open), write-before reload optimistic concurrency via `Session.ensure_fresh_novel`. Real-API run verified; low-rpm services should increase the call interval in `/setting`.
- Environment managed with `uv` (do NOT use system python, which is 3.9 and too old). `uv.lock` is committed; dev deps live in `[dependency-groups] dev`; runtime deps (pydantic) go in `[project] dependencies` then `uv sync --dev`.
- No CI, no linter/formatter configured.

## Working conventions

- Commands: `uv sync --dev` to create/refresh `.venv`, then `uv run pytest` for tests and `uv run opennovel` for the CLI. Dependencies go in `[dependency-groups]` (new-style uv), not `optional-dependencies`.
- Keep `README.md` in sync with the code: update it in the same change whenever files, commands, or structure change (user requirement).
- Plans, design notes, and session records live in `docs/` (`docs/work-log.md`): append a short entry after each working session. `docs/` is gitignored — never commit it.
- The user communicates product requirements in Chinese; keep product-facing terminology bilingual where useful (e.g., 剧情 / plot).
