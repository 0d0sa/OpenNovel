# AGENTS.md

## Project goal

Build an agent that writes novels: the user supplies a plot (剧情), and the agent produces novel scenes/fragments and chapters. Two non-negotiable quality requirements, per novel:

- **Language style consistency** (语言风格一致性): the writing voice/style must stay uniform across the whole novel.
- **Plot coherence** (剧情连贯性): events, characters, and setups must remain consistent across chapters.

Treat these as first-class architectural constraints, not afterthoughts. Any design (prompt scaffolding, memory/state, per-novel context, style anchors) should explicitly serve them.

## Repo state

- Python CLI scaffold only: `pyproject.toml` (hatchling, src layout), `src/opennovel/` placeholder modules, `tests/` smoke tests. No real agent logic yet.
- Decisions already made: Python, CLI tool, native LLM SDK hand-written orchestration (no agent framework). LLM provider: openai SDK against OpenAI-compatible services (DeepSeek/通义/智谱/etc. via `base_url`), configured by env vars (`OPENNOVEL_LLM_API_KEY` / `OPENNOVEL_LLM_MODEL` / `OPENNOVEL_LLM_BASE_URL`). SDK usage must stay inside `llm/` — never import it in upper layers.
- Data models are done (MVP step 1): Pydantic v2, `Novel` as aggregate root holding `style_profile`/`plot_state`, JSON persistence per book (`novels/<title>/novel.json`). Style memory is done (MVP step 3): one-time upfront extraction + anchor-block injection + chapter-level deviation check (`memory/style_profile.py`), toggled by `OPENNOVEL_STYLE_CHECK`. Plot memory is done (MVP step 4): incremental LLM extraction + deterministic merge, compressed brief injection, chapter-level consistency check (`memory/plot_state.py`), toggled by `OPENNOVEL_PLOT_CHECK`. Orchestration (剧情 -> chapters) is done (MVP step 5): `agent/planning.py` (outline/scenes/writing/rewrite prompts) + `agent/orchestrator.py` (`write_novel`, per-chapter save + novel.txt export), CLI `opennovel write`. Interactive UI is done on branch `frontend` (MVP step 6): rich-based REPL (`ui/repl.py` + `ui/display.py`), streaming output (`Provider.stream_complete`), per-chapter check reports stored on `Chapter.style_report`/`plot_report`. Chat-style UI is done on branch `frontend` (MVP step 7): prompt_toolkit input (`ui/input.py`, multiline/history/`/` completion), chat stream (`ui/chat.py`), LLM intent routing for free text (`agent/intent.py`, fallback to append-plot on failure). Real-API run verified; the gateway used (sensenova) has a very low rpm — set `OPENNOVEL_LLM_INTERVAL` (e.g. 20) for real runs.
- Environment managed with `uv` (do NOT use system python, which is 3.9 and too old). `uv.lock` is committed; dev deps live in `[dependency-groups] dev`; runtime deps (pydantic) go in `[project] dependencies` then `uv sync --dev`.
- No CI, no linter/formatter configured.

## Working conventions

- Commands: `uv sync --dev` to create/refresh `.venv`, then `uv run pytest` for tests and `uv run opennovel` for the CLI. Dependencies go in `[dependency-groups]` (new-style uv), not `optional-dependencies`.
- Keep `README.md` in sync with the code: update it in the same change whenever files, commands, or structure change (user requirement).
- Plans, design notes, and session records live in `docs/` (`docs/work-log.md`): append a short entry after each working session. `docs/` is gitignored — never commit it.
- The user communicates product requirements in Chinese; keep product-facing terminology bilingual where useful (e.g., 剧情 / plot).
