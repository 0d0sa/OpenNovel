"""Shared visual tokens for the terminal interfaces."""

from prompt_toolkit.styles import Style

# Warm brand color inspired by Claude Code, paired with the cool, quiet
# neutrals used by Codex CLI.  Rich accepts the same hex values.
BRAND = "#d97757"
ACCENT = "#7aa2f7"
TEXT = "#d7dde5"
MUTED = "#7d8590"
SUBTLE = "#303842"
SUCCESS = "#7fb069"
WARNING = "#d7a65a"
ERROR = "#e06c75"


UI_STYLE = Style.from_dict(
    {
        "root": f"bg:#0d1117 {TEXT}",
        "header": "bg:#161b22",
        "header.brand": f"bold {BRAND}",
        "header.title": f"bold {TEXT}",
        "header.meta": f"{MUTED}",
        "history": "bg:#0d1117",
        "composer.rule": f"{SUBTLE}",
        "composer.label": f"bold {MUTED}",
        "composer.input": f"bg:#0d1117 {TEXT}",
        "composer.prompt": f"bold {BRAND}",
        "footer": f"bg:#0d1117 {MUTED}",
        "footer.key": f"bold {TEXT}",
        "status.ready": f"bold {SUCCESS}",
        "status.busy": f"bold {WARNING}",
        "status.ask": f"bold {ACCENT}",
        "completion-menu": f"bg:#161b22 {TEXT}",
        "completion-menu.completion": f"bg:#161b22 {TEXT}",
        "completion-menu.completion.current": f"bg:#30363d {BRAND}",
        "completion-menu.meta.completion": f"bg:#161b22 {MUTED}",
        "completion-menu.meta.completion.current": f"bg:#30363d {TEXT}",
        "scrollbar.background": "bg:#161b22",
        "scrollbar.button": "bg:#484f58",
    }
)
