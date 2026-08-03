"""Smoke test: package imports and CLI parser work."""

from opennovel import __version__
from opennovel.cli import build_parser


def test_version():
    assert __version__ == "0.1.0"


def test_cli_parser_has_write_command():
    parser = build_parser()
    assert "write" in [a.dest for a in parser._actions] or any(
        getattr(a, "choices", None) and "write" in a.choices for a in parser._actions
    )
