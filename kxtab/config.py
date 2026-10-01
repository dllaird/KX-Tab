"""Settings, read from KXTAB_* environment variables at call time."""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    tickers: tuple[str, ...]
    series_status: str = "open"
    daily_days: float = 400
    hourly_days: float = 8
    minute_hours: float = 0
    trades_days: float = 7
    max_markets: int = 300
    max_trades: int = 200_000


def _num(name: str, default: float, cast=float):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None
    if value < 0:
        raise ConfigError(f"{name} must be >= 0, got {raw!r}")
    return value


def load(ticker: str | None = None) -> Config:
    """Config from the environment; `ticker` overrides KXTAB_TICKER."""
    raw = ticker if ticker is not None else os.environ.get("KXTAB_TICKER", "")
    tickers = tuple(dict.fromkeys(t.strip().upper() for t in raw.split(",") if t.strip()))
    if not tickers:
        raise ConfigError("Set KXTAB_TICKER to a Kalshi series, event or market ticker (comma-separated for several), "
                          "then restart TabPy.")
    status = os.environ.get("KXTAB_SERIES_STATUS", "open").strip().lower() or "open"
    if status not in ("open", "all"):
        raise ConfigError(f"KXTAB_SERIES_STATUS must be 'open' or 'all', got {status!r}")
    return Config(
        tickers=tickers,
        series_status=status,
        daily_days=_num("KXTAB_DAILY_DAYS", 400),
        hourly_days=_num("KXTAB_HOURLY_DAYS", 8),
        minute_hours=_num("KXTAB_MINUTE_HOURS", 0),
        trades_days=_num("KXTAB_TRADES_DAYS", 7),
        max_markets=int(_num("KXTAB_MAX_MARKETS", 300, int)),
        max_trades=int(_num("KXTAB_MAX_TRADES", 200_000, int)),
    )
