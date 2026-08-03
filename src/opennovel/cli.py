"""CLI entry point (scaffold only, no real commands yet)."""

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="opennovel", description="Novel-writing agent CLI")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("write", help="write a novel from a plot (not implemented yet)")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return 0
    raise NotImplementedError("agent logic not implemented yet")


if __name__ == "__main__":
    raise SystemExit(main())
