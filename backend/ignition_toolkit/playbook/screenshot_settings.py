"""
Screenshot path settings — stored in toolkit-data dir alongside other settings.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ignition_toolkit.core.paths import get_screenshots_dir, get_user_data_dir

# Matches {#}, {##}, {###}, … anywhere in the template.
# Group 1 = the hash chars, Group 2 = any trailing separator chars (e.g. "_")
_COUNTER_RE = re.compile(r'\{(#+)\}([^{]*?)$')


def _settings_path() -> Path:
    return get_user_data_dir() / "screenshot_settings.json"


def get_screenshot_settings() -> dict[str, Any]:
    p = _settings_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"enabled": False, "path_template": ""}


def save_screenshot_settings(enabled: bool, path_template: str) -> None:
    p = _settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"enabled": enabled, "path_template": path_template}, indent=2), encoding="utf-8")


def _sanitize(name: str) -> str:
    """Make a string safe for use as a directory name."""
    return re.sub(r'[<>:"/\\|?*\s]+', "_", name).strip("_") or "playbook"


def _format_counter(n: int, width: int) -> str:
    """Format counter with optional zero-padding. width=1 → no padding."""
    return str(n) if width <= 1 else f"{n:0{width}d}"


def resolve_screenshot_config(playbook_name: str) -> tuple[Path, int, str]:
    """
    Return (screenshots_dir, counter_width, counter_sep) for this execution.

    counter_width=0 means no counter prefix on filenames.
    counter_width=1 means plain integer (1, 2, 10 …).
    counter_width>=2 means zero-padded (01, 02, 10 … for width=2).
    counter_sep is the text that follows the counter before the filename (e.g. "_").

    Falls back to (default_dir, 0, '') on any error or when disabled.

    Path template variables:
        {playbook_name}  — sanitized playbook name
        {date}           — YYYY-MM-DD
        {datetime}       — YYYY-MM-DD_HH-MM-SS
        {year}           — four-digit year
        {month}          — zero-padded month
        {day}            — zero-padded day
        {time}           — HH-MM-SS

    Counter variables (stripped from dir template, applied per screenshot):
        {#}              — plain integer  (1, 2, 3 …)
        {##}             — 2-digit padded (01, 02, 03 …)
        {###}            — 3-digit padded (001, 002, 003 …)
    """
    default = get_screenshots_dir()
    try:
        settings = get_screenshot_settings()
        if not settings.get("enabled") or not settings.get("path_template", "").strip():
            return default, 0, ""

        template = settings["path_template"].strip()

        # Extract counter pattern before passing to str.format()
        counter_width = 0
        counter_sep = ""
        m = _COUNTER_RE.search(template)
        if m:
            counter_width = len(m.group(1))
            counter_sep = m.group(2)
            template = template[: m.start()]  # strip counter from dir template

        now = datetime.now()
        variables = {
            "playbook_name": _sanitize(playbook_name),
            "date":          now.strftime("%Y-%m-%d"),
            "datetime":      now.strftime("%Y-%m-%d_%H-%M-%S"),
            "year":          now.strftime("%Y"),
            "month":         now.strftime("%m"),
            "day":           now.strftime("%d"),
            "time":          now.strftime("%H-%M-%S"),
        }

        resolved = template.format(**variables)
        path = Path(resolved)
        if not path.is_absolute():
            path = default / path
        path.mkdir(parents=True, exist_ok=True)

        return path, counter_width, counter_sep
    except Exception:
        return default, 0, ""


def format_counter(n: int, width: int, sep: str) -> str:
    """Return the filename prefix for screenshot number n."""
    if width == 0:
        return ""
    return f"{_format_counter(n, width)}{sep}"
