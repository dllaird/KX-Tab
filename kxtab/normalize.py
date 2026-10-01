"""Flatten Kalshi JSON into Tableau-friendly columns: canonical names, numbers, UTC time strings."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

NUMERIC_SUFFIXES = ("_dollars", "_fp")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def canon(key: str) -> str:
    """Drop Kalshi's unit suffixes so live and historical fields share names (yes_bid_dollars -> yes_bid)."""
    for suffix in NUMERIC_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)]
    return key


def to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_utc(value: Any) -> str | None:
    """ISO string or epoch seconds -> 'YYYY-MM-DD HH:MM:SS' (UTC). Placeholder dates (year 1) -> None."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return str(value)
    return None if dt.year < 1900 else dt.strftime(TIME_FORMAT)


def _is_time(key: str) -> bool:
    return key.endswith("_time") or key.endswith("_ts")


def flatten(obj: dict, prefix: str = "") -> dict[str, Any]:
    """Nested dicts joined with '_', suffixes dropped, numbers parsed, times as UTC strings, lists as JSON."""
    out: dict[str, Any] = {}
    for key, value in obj.items():
        name = prefix + canon(key)
        numeric = key.endswith(NUMERIC_SUFFIXES)
        if isinstance(value, dict):
            out.update(flatten(value, name + "_"))
        elif isinstance(value, list):
            out[name] = json.dumps(value, separators=(",", ":"))
        elif numeric:
            out[name] = to_float(value)
        elif _is_time(key):
            out[name] = to_utc(value)
        else:
            out[name] = value
    return out


CANDLE_NUMERIC = ("yes_bid", "yes_ask", "price")
CANDLE_FIELDS = [f"{g}_{k}" for g in ("yes_bid", "yes_ask") for k in ("open", "high", "low", "close")] + \
    [f"price_{k}" for k in ("open", "high", "low", "close", "mean", "previous")] + ["volume", "open_interest"]


def candle(c: dict) -> dict[str, Any]:
    """One candle -> flat row with every CANDLE_FIELDS key. Live (close_dollars) and historical (close) match."""
    row: dict[str, Any] = {"time_utc": to_utc(c.get("end_period_ts")), **dict.fromkeys(CANDLE_FIELDS)}
    for group in CANDLE_NUMERIC:
        for key, value in (c.get(group) or {}).items():
            row[f"{group}_{canon(key)}"] = to_float(value)
    for key in ("volume", "open_interest"):
        row[key] = to_float(c.get(key + "_fp", c.get(key)))
    return row
