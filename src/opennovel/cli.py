"""CLI entry point: `opennovel` enters the interactive REPL, `opennovel write`
runs the batch pipeline."""

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opennovel",
        description="Novel-writing agent CLI（不带子命令进入交互模式）",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    sub = parser.add_subparsers(dest="command")

    write = sub.add_parser("write", help="write a novel from a plot")
    write.add_argument("--title", required=True, help="书名（决定输出目录 novels/<title>/）")
    write.add_argument("--plot", help="剧情文本")
    write.add_argument("--plot-file", help="剧情文本文件路径（与 --plot 二选一）")
    write.add_argument("--style", default="", help="可选：风格描述，如 冷峻/诙谐/诗意")
    write.add_argument("--max-chapters", type=int, default=None, help="覆盖 OPENNOVEL_MAX_CHAPTERS")
    return parser


def main() -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        return _cmd_interactive()
    if args.command == "write":
        return _cmd_write(args)
    return 1


def _cmd_interactive() -> int:
    from opennovel.config import load_settings
    from opennovel.llm import ProviderConfigError, provider_from_env

    try:
        provider = provider_from_env()
    except ProviderConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    settings = load_settings()
    try:
        from opennovel.ui.app import FullScreenChatApp

        return FullScreenChatApp(provider, settings).run()
    except Exception:
        from opennovel.ui import run_repl

        return run_repl(provider, settings)


def _cmd_write(args: argparse.Namespace) -> int:
    from opennovel.agent import write_novel
    from opennovel.config import load_settings
    from opennovel.llm import ProviderConfigError, provider_from_env

    plot = ""
    if args.plot_file:
        try:
            plot = Path(args.plot_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"读取剧情文件失败：{exc}", file=sys.stderr)
            return 1
    elif args.plot:
        plot = args.plot
    if not plot.strip():
        print("缺少剧情：请用 --plot 或 --plot-file 提供剧情", file=sys.stderr)
        return 1

    try:
        provider = provider_from_env()
    except ProviderConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1

    settings = load_settings()
    if args.max_chapters is not None:
        settings = replace(settings, max_chapters=args.max_chapters)

    novel = write_novel(provider, settings, args.title, plot, args.style, on_progress=print)

    n_chars = sum(len(s.content) for ch in novel.chapters for s in ch.scenes)
    print(f"\n完成：《{novel.title}》{len(novel.chapters)} 章，共约 {n_chars} 字")
    print(f"成书：{settings.output_dir}/{novel.title}/novel.json 与 novel.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
