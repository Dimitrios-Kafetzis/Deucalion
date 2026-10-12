"""Screenshot mode for the documentation (no GTK imports here, so it can be tested anywhere)."""

from __future__ import annotations


def parse_screenshot_entries(text: str, default_wait: int = 1200) -> list[tuple[str, str, str, str, int]]:
    """DEUCALION_SCREENSHOT_PAGES: entries separated by ';' (or ',' when no entry has arguments).

    An entry is   [name=]page[:action[(argument)]][@milliseconds]
      page        a sidebar page (overview, backup, …) or 'win' for the window itself
      action      calls screenshot_<action>(argument) on that page (or window); if it returns
                  'wait', it is called again every second until it returns something else
      name        the PNG's name (default: the entry with ':' as '-'); '_' takes no picture
      @ms         how long to wait before taking the picture
    Returns [(name, page, action, argument, wait)]."""
    sep = ";" if ";" in text or "(" in text else ","
    out = []
    for raw in text.split(sep):
        raw = raw.strip()
        if not raw:
            continue
        name, eq, rest = raw.partition("=")
        if not eq:
            name, rest = "", raw
        wait = default_wait
        if "@" in rest and rest.rsplit("@", 1)[1].isdigit():
            rest, ms = rest.rsplit("@", 1)
            wait = int(ms)
        page, _, action = rest.partition(":")
        arg = ""
        if action.endswith(")") and "(" in action:
            action, arg = action[:-1].split("(", 1)
        out.append((name or rest.replace(":", "-").replace("(", "-").rstrip(")"), page, action, arg, wait))
    return out
