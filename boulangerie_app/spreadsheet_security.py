from __future__ import annotations

from typing import Any


SPREADSHEET_FORMULA_PREFIXES = ("=", "+", "-", "@")


def sanitize_spreadsheet_value(value: Any) -> Any:
    """Keep user-controlled text from being interpreted as a spreadsheet formula."""
    if not isinstance(value, str):
        return value
    probe = value.lstrip(" \t\r\n")
    if probe.startswith(SPREADSHEET_FORMULA_PREFIXES):
        return "'" + value
    return value
