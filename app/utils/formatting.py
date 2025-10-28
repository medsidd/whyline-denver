"""Formatting utilities for display."""

from __future__ import annotations

from datetime import datetime


def human_readable_bytes(value: int | None) -> str:
    """Convert bytes to human-readable format (KB, MB, GB, etc.)."""
    if value is None:
        return "unknown"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} {units[-1]}"


def format_timestamp(ts: str | None) -> str:
    """Format ISO timestamp to human-readable string."""
    if not ts:
        return "Unavailable"
    try:
        if ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(ts)
        return parsed.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        try:
            parsed = datetime.utcfromtimestamp(float(ts))
            return parsed.strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, TypeError):
            return ts
