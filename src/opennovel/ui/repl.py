"""Chat-style interactive session (Claude Code like).

`opennovel` with no subcommand enters. `/` commands and free-text prompts are
both accepted in the same input box; free text goes through LLM intent routing
(`agent/intent.py`). Command dispatch stays in `handle_command` (pure-ish,
testable without a terminal).
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from opennovel.agent import IntentKind, classify_intent, write_novel
from opennovel.config import Settings
from opennovel.llm import Provider
from opennovel.models import Scene, SceneStatus, save_novel
from opennovel.ui.chat import ChatStream
from opennovel.ui.display import print_banner, print_checks, print_help, print_status, print_style
from opennovel.ui.input import ChatInput


@dataclass
class Session:
    provider: Provider
    settings: Settings
    console: Console
    chat: ChatStream
    title: str = ""
    plot: str = ""
    style_hint: str = ""
    novel: object = None
    history: list[str] = field(default_factory=list)
    exiting: bool = False
    user_settings: object = None
    on_provider_change: object = None
    settings_path: Path | None = None

    def ensure_user_settings(self):
        """Load user settings file (cached); returns UserSettings or None."""
        if self.user_settings is None:
            from opennovel.settings_store import load_user_settings

            self.user_settings = load_user_settings(self.settings_path)
        return self.user_settings

    def switch_provider(self, profile) -> None:
        """Rebuild the provider from a profile and notify the UI."""
        from opennovel.llm import build_provider_from_profile

        self.provider = build_provider_from_profile(profile, self.settings)
        if self.on_provider_change is not None:
            self.on_provider_change()

    def save_profile(self, profile, runtime=None) -> None:
        """Persist a profile and runtime settings, then apply them live."""
        from opennovel.config import settings_from_user_settings
        from opennovel.settings_store import UserSettings, save_user_settings

        user_settings = self.ensure_user_settings() or UserSettings()
        user_settings.profiles[profile.name] = profile
        user_settings.active = profile.name
        if runtime is not None:
            user_settings.runtime = runtime
        save_user_settings(user_settings, self.settings_path)
        self.user_settings = user_settings
        self.settings = settings_from_user_settings(user_settings)
        self.switch_provider(profile)

    def save_runtime(self, runtime) -> None:
        """Persist global runtime settings and apply them to the session."""
        from opennovel.config import settings_from_user_settings
        from opennovel.settings_store import UserSettings, save_user_settings

        user_settings = self.ensure_user_settings() or UserSettings()
        user_settings.runtime = runtime
        save_user_settings(user_settings, self.settings_path)
        self.user_settings = user_settings
        self.settings = settings_from_user_settings(user_settings)
        profile = user_settings.active_profile()
        if profile is not None:
            self.switch_provider(profile)

    def ask(self, prompt: str, *, secret: bool = False) -> str:
        """Read a line, dispatching `/` commands instead of treating them as answers."""
        while True:
            formatted_prompt = f"[bold cyan]{prompt}[/bold cyan] "
            if secret:
                line = self.console.input(formatted_prompt, password=True).strip()
            else:
                line = self.console.input(formatted_prompt).strip()
            if line.startswith("/"):
                handle_command(self, line)
                if self.exiting:
                    return ""
                self.console.print("[dim]命令已执行，请继续回答：[/dim]" + prompt)
                continue
            if secret and line:
                self.chat.add_user("••••••••")
            elif line:
                self.chat.add_user(line)
            return line

    def say(self, text: str) -> None:
        self.console.print(text)

    def show_status(self) -> None:
        print_status(self.console, self.novel)

    def show_style(self) -> None:
        print_style(self.console, getattr(self.novel, "style_profile", None))

    def show_checks(self) -> None:
        print_checks(self.console, self.novel)

    def show_help(self) -> None:
        print_help(self.console)


def run_repl(provider: Provider, settings: Settings) -> int:
    console = Console()
    session = Session(provider=provider, settings=settings, console=console, chat=ChatStream(console))
    print_banner(console)
    print_help(console)
    inp = ChatInput()
    while True:
        try:
            line = inp.prompt()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见[/dim]")
            return 0
        line = line.strip()
        if not line:
            continue
        session.history.append(line)
        session.chat.add_user(line)
        try:
            if not handle_command(session, line) or session.exiting:
                return 0
        except Exception as exc:
            console.print(f"[red]错误：{exc}[/red]")


def handle_command(session: Session, line: str) -> bool:
    """Process one input line. Returns False to exit the session."""
    if line.startswith("/"):
        parts = _split_command(line)
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd == "/exit":
            session.exiting = True
            return False
        if cmd == "/help":
            session.show_help()
        elif cmd == "/new":
            _cmd_new(session, args)
        elif cmd == "/write":
            _cmd_write(session)
        elif cmd == "/status":
            session.show_status()
        elif cmd == "/style":
            session.show_style()
        elif cmd == "/checks":
            session.show_checks()
        elif cmd == "/rewrite":
            _cmd_rewrite(session, args)
        elif cmd == "/setting":
            _cmd_setting(session, args)
        elif cmd == "/model":
            _cmd_model(session, args)
        else:
            session.say(f"[red]未知命令：{cmd}（/help 查看可用命令）[/red]")
    else:
        _route_free_text(session, line)
    return True


def _split_command(line: str) -> list[str]:
    """Split slash commands without treating Windows path slashes as escapes."""
    parts = shlex.split(line, posix=os.name != "nt")
    if os.name == "nt":
        parts = [
            part[1:-1]
            if len(part) >= 2 and part[0] == part[-1] and part[0] in {'"', "'"}
            else part
            for part in parts
        ]
    return parts


def _route_free_text(session: Session, line: str) -> None:
    intent = classify_intent(session.provider, line)
    kind = intent.kind
    if kind == IntentKind.REWRITE_CHAPTER and intent.chapter_no >= 1:
        _cmd_rewrite(session, [str(intent.chapter_no)])
    elif kind == IntentKind.START_NEW:
        _cmd_new(session, [])
    elif kind == IntentKind.WRITE_NOW:
        _cmd_write(session)
    elif kind == IntentKind.STATUS:
        session.show_status()
    elif kind == IntentKind.CHECKS:
        session.show_checks()
    elif kind == IntentKind.HELP:
        session.show_help()
    else:  # append_plot / other
        if kind == IntentKind.OTHER and intent.suggestion:
            session.say(f"（{_plain(intent.suggestion)}）")
        _append_plot(session, line)


def _plain(text: str) -> str:
    """Strip rich-markup-like [tag] tokens (LLM output safety)."""
    import re

    return re.sub(r"\[/?[a-zA-Z_][a-zA-Z0-9_]*\]", "", text)


def _cmd_setting(session: Session, args: list[str]) -> None:
    """Manage the complete application configuration."""
    from opennovel.settings_store import ProfileConfig

    if "--list" in args:
        _list_profiles(session)
        return
    if "--remove" in args:
        idx = args.index("--remove")
        if idx + 1 >= len(args):
            session.say("[red]用法：/setting --remove NAME[/red]")
            return
        _remove_profile(session, args[idx + 1])
        return

    flags = {}
    setting_flags = (
        "--name",
        "--base-url",
        "--api-key",
        "--model",
        "--temperature",
        "--max-tokens",
        "--interval",
        "--language",
        "--chapter-target-chars",
        "--max-chapters",
        "--output-dir",
        "--style-check",
        "--plot-check",
    )
    for key in setting_flags:
        if key in args:
            i = args.index(key)
            if i + 1 >= len(args):
                session.say(f"[red]{key} 缺少值[/red]")
                return
            flags[key[2:].replace("-", "_")] = args[i + 1]

    profile_flag_names = {"name", "base_url", "api_key", "model"}
    has_profile_flags = bool(profile_flag_names.intersection(flags))
    has_runtime_flags = bool(set(flags) - profile_flag_names)
    if flags:
        user_settings = session.ensure_user_settings()
        if user_settings:
            current_runtime = user_settings.runtime
        else:
            from opennovel.config import runtime_from_settings

            current_runtime = runtime_from_settings(session.settings)
        runtime = _runtime_from_values(current_runtime, flags)
        if runtime is None:
            session.say("[red]生成参数格式错误，请检查数字范围和 on/off 开关[/red]")
            return
        if has_runtime_flags and not has_profile_flags:
            session.save_runtime(runtime)
            session.say("[green]运行设置已保存并立即生效[/green]")
            return
        name = flags.get("name")
        api_key = flags.get("api_key")
        model = flags.get("model")
        if not name or not api_key or not model:
            session.say("[red]参数式设置需提供 --name --api-key --model（--base-url 可选）[/red]")
            return
        profile = ProfileConfig(
            name=name,
            base_url=flags.get("base_url") or None,
            api_key=api_key,
            model=model,
        )
        _save_and_activate(session, profile, runtime)
        return

    # wizard
    name = session.ask("配置名（如 deepseek）：")
    if session.exiting:
        return
    if not name:
        session.say("[red]配置名不能为空[/red]")
        return
    base_url = session.ask("base URL（回车跳过 = OpenAI 官方）：")
    if session.exiting:
        return
    api_key = session.ask("API key：", secret=True)
    if session.exiting:
        return
    if not api_key:
        session.say("[red]API key 不能为空[/red]")
        return
    model = session.ask("模型名：")
    if session.exiting:
        return
    if not model:
        session.say("[red]模型名不能为空[/red]")
        return
    current = session.ensure_user_settings()
    if current:
        runtime = current.runtime
    else:
        from opennovel.config import runtime_from_settings

        runtime = runtime_from_settings(session.settings)
    answers = {}
    prompts = [
        ("temperature", f"采样温度（当前 {runtime.temperature}）："),
        ("max_tokens", f"单次最大 token（当前 {runtime.max_tokens}）："),
        ("interval", f"调用间隔秒数（当前 {runtime.call_interval}）："),
        ("language", f"成书语言（当前 {runtime.language}）："),
        ("chapter_target_chars", f"每章目标字数（当前 {runtime.chapter_target_chars}）："),
        ("max_chapters", f"最大章节数（当前 {runtime.max_chapters}）："),
        ("output_dir", f"输出目录（当前 {runtime.output_dir}）："),
        ("style_check", f"风格检查 on/off（当前 {_on_off(runtime.style_check)}）："),
        ("plot_check", f"剧情检查 on/off（当前 {_on_off(runtime.plot_check)}）："),
    ]
    for key, prompt in prompts:
        value = session.ask(prompt)
        if session.exiting:
            return
        if value:
            answers[key] = value
    runtime = _runtime_from_values(runtime, answers)
    if runtime is None:
        session.say("[red]生成参数格式错误，请重新执行 /setting[/red]")
        return
    profile = ProfileConfig(name=name, base_url=base_url or None, api_key=api_key, model=model)
    _save_and_activate(session, profile, runtime)


def _save_and_activate(session: Session, profile, runtime=None) -> None:
    session.save_profile(profile, runtime)
    session.say(f"[green]已保存并切换到 {profile.name}（{profile.model}）[/green]")


def _runtime_from_values(current, values: dict[str, str]):
    """Overlay slash-command/form values on a RuntimeConfig."""
    from opennovel.settings_store import RuntimeConfig

    data = current.model_dump()
    aliases = {
        "interval": "call_interval",
    }
    bool_fields = {"style_check", "plot_check"}
    try:
        for key, value in values.items():
            target = aliases.get(key, key)
            if target not in data:
                continue
            data[target] = _parse_switch(value) if target in bool_fields else value
        return RuntimeConfig.model_validate(data)
    except (TypeError, ValueError):
        return None


def _parse_switch(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "on", "yes", "是", "开"}:
        return True
    if normalized in {"0", "false", "off", "no", "否", "关"}:
        return False
    raise ValueError(f"invalid switch: {value}")


def _on_off(value: bool) -> str:
    return "on" if value else "off"


def _list_profiles(session: Session) -> None:
    us = session.ensure_user_settings()
    if us is None:
        from opennovel.config import runtime_from_settings
        from opennovel.settings_store import UserSettings

        us = UserSettings(runtime=runtime_from_settings(session.settings))
    from opennovel.settings_store import mask_key

    lines = ["[bold]已配置的模型：[/bold]"]
    if not us.profiles:
        lines.append("  [yellow]暂无模型，用 /setting 添加[/yellow]")
    else:
        for i, (name, p) in enumerate(us.profiles.items(), 1):
            mark = "[green]*[/green]" if name == us.active else " "
            lines.append(
                f"  {mark} {i}. {name}  {p.model}  "
                f"{p.base_url or 'OpenAI 官方'}  {mask_key(p.api_key)}"
            )
    runtime = us.runtime
    lines.extend(
        [
            "[bold]生成参数：[/bold]",
            f"  temperature={runtime.temperature}  max_tokens={runtime.max_tokens}  "
            f"interval={runtime.call_interval}s",
            f"  language={runtime.language}  chapter_chars={runtime.chapter_target_chars}  "
            f"max_chapters={runtime.max_chapters}",
            f"  output_dir={runtime.output_dir}  style_check={_on_off(runtime.style_check)}  "
            f"plot_check={_on_off(runtime.plot_check)}",
        ]
    )
    session.say("\n".join(lines))


def _remove_profile(session: Session, name: str) -> None:
    from opennovel.settings_store import UserSettings, save_user_settings

    us = session.ensure_user_settings() or UserSettings()
    if name not in us.profiles:
        session.say(f"[red]未找到配置：{name}[/red]")
        return
    was_active = us.active == name
    del us.profiles[name]
    if was_active:
        us.active = ""
    save_user_settings(us, session.settings_path)
    session.user_settings = us
    if was_active:
        from opennovel.config import settings_from_user_settings
        from opennovel.llm import UnconfiguredProvider

        session.settings = settings_from_user_settings(us)
        session.provider = UnconfiguredProvider()
        if session.on_provider_change is not None:
            session.on_provider_change()
    session.say(f"[green]已删除配置：{name}[/green]")


def _cmd_model(session: Session, args: list[str]) -> None:
    """Switch the active model profile."""
    us = session.ensure_user_settings()
    if us is None or not us.profiles:
        session.say("[yellow]还没有任何配置，先 /setting 添加[/yellow]")
        return
    target = args[0] if args else ""
    if not target:
        _list_profiles(session)
        target = session.ask("输入配置名或序号切换（回车取消）：")
        if session.exiting or not target:
            return
    if target.isdigit():
        names = list(us.profiles)
        idx = int(target)
        if not 1 <= idx <= len(names):
            session.say(f"[red]序号超出范围（1-{len(names)}）[/red]")
            return
        target = names[idx - 1]
    profile = us.profiles.get(target)
    if profile is None:
        session.say(f"[red]未找到配置：{target}[/red]")
        return
    if profile.name == us.active:
        session.say(f"[dim]当前已在使用 {target}[/dim]")
        return
    us.active = profile.name
    from opennovel.settings_store import save_user_settings

    save_user_settings(us, session.settings_path)
    session.user_settings = us
    from opennovel.config import settings_from_user_settings

    session.settings = settings_from_user_settings(us)
    session.switch_provider(profile)
    session.say(f"[green]已切换到 {profile.name}（{profile.model}）[/green]")


def _append_plot(session: Session, line: str) -> None:
    if not session.plot:
        session.say("[yellow]还没有开始新书，先 /new 创建[/yellow]")
        return
    session.plot = session.plot.rstrip() + "\n" + line
    session.say("[dim]已追加到剧情[/dim]")


def _cmd_new(session: Session, args: list[str]) -> None:
    title = ""
    plot_file = None
    style_hint = ""
    i = 0
    while i < len(args):
        if args[i] == "--title" and i + 1 < len(args):
            title = args[i + 1]
            i += 2
        elif args[i] == "--plot-file" and i + 1 < len(args):
            plot_file = args[i + 1]
            i += 2
        elif args[i] == "--style" and i + 1 < len(args):
            style_hint = args[i + 1]
            i += 2
        else:
            session.say(f"[red]未知参数：{args[i]}（支持 --title / --plot-file / --style）[/red]")
            return
    title = title or session.ask("书名：")
    if session.exiting:
        return
    if not title:
        session.say("[red]书名不能为空[/red]")
        return
    plot = ""
    if plot_file:
        try:
            plot = Path(plot_file).read_text(encoding="utf-8")
        except OSError as exc:
            session.say(f"[red]读取剧情文件失败：{exc}[/red]")
            return
    else:
        plot = session.ask("剧情（一句话即可）：")
        if session.exiting:
            return
    if not plot:
        session.say("[red]剧情不能为空[/red]")
        return
    style_hint = style_hint or session.ask("风格描述（可回车跳过）：")
    if session.exiting:
        return
    session.title = title
    session.plot = plot
    session.style_hint = style_hint
    session.novel = None
    session.chat.add_system(session.chat.stage_panel(f"已创建：《{title}》，说 /write 或“开始写作”"))
    session.say("[dim]聊天输入可理解为自然语言指令（如“把第二章重写得更紧张”）[/dim]")


def _cmd_write(session: Session) -> None:
    if not session.plot:
        session.say("[yellow]还没有开始新书，先 /new 创建[/yellow]")
        return

    def on_stage(stage: str) -> None:
        session.chat.add_system(session.chat.stage_panel(stage))

    session.chat.begin_stream()
    novel = write_novel(
        session.provider,
        session.settings,
        session.title,
        session.plot,
        session.style_hint,
        on_progress=session.say,
        on_stage=on_stage,
        on_token=session.chat.feed,
    )
    session.chat.end_stream()
    session.novel = novel
    session.chat.add_system(session.chat.summary_card(novel))
    path = session.settings.output_dir / novel.title / "novel.json"
    session.say(f"[dim]成书：{path}（/checks 查看检查报告）[/dim]")


def _cmd_rewrite(session: Session, args: list[str]) -> None:
    novel = session.novel
    if novel is None:
        session.say("[yellow]还没有章节可重写[/yellow]")
        return
    if not args:
        session.say("[red]用法：/rewrite N 或直接说“重写第N章”[/red]")
        return
    try:
        idx = int(args[0])
    except ValueError:
        session.say("[red]章节号必须是数字[/red]")
        return
    if not 1 <= idx <= len(novel.chapters):
        session.say(f"[red]章节号超出范围（1-{len(novel.chapters)}）[/red]")
        return

    from opennovel.agent.planning import rewrite_chapter
    from opennovel.memory import style_anchor_block

    chapter = novel.chapters[idx - 1]
    text = "\n\n".join(s.content for s in chapter.scenes if s.content)
    if not text:
        session.say("[red]该章无正文[/red]")
        return
    session.chat.add_system(session.chat.stage_panel(f"重写第{idx}章…"))

    session.chat.begin_stream()
    new_text = rewrite_chapter(
        session.provider,
        text,
        chapter.style_report,
        chapter.plot_report,
        style_anchor_block(novel.style_profile),
        stream_callback=session.chat.feed,
    )
    session.chat.end_stream()
    chapter.scenes = [Scene(summary="重写稿", content=new_text, status=SceneStatus.WRITTEN)]
    chapter.style_report = None
    chapter.plot_report = None
    save_novel(novel, session.settings.output_dir / novel.title / "novel.json")
    session.say(f"[green]第{idx}章已重写并保存[/green]")
