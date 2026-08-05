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


def test_cli_main_enters_interactive_without_loading_env(monkeypatch):
    import opennovel.cli as cli

    entered = []
    monkeypatch.setattr(cli, "_cmd_interactive", lambda: entered.append(1) or 0)
    monkeypatch.setattr("sys.argv", ["opennovel"])
    cli.main()
    assert entered == [1]


def test_interactive_starts_without_provider_config(monkeypatch, tmp_path):
    import opennovel.cli as cli
    import opennovel.llm as llm
    from opennovel.ui.app import FullScreenChatApp

    def missing_provider(*args, **kwargs):
        raise llm.ProviderConfigError("missing")

    started = []
    monkeypatch.setattr(llm, "provider_from_settings", missing_provider)
    monkeypatch.setattr(
        FullScreenChatApp,
        "run",
        lambda self: started.append(self.session.provider) or 0,
    )

    assert cli._cmd_interactive() == 0
    assert isinstance(started[0], llm.UnconfiguredProvider)
