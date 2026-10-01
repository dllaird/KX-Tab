"""KX-Tab: Kalshi market data as Tableau table extensions (TabPy). Set KXTAB_TICKER, then e.g.

    import kxtab
    return kxtab.history()
"""
from __future__ import annotations

import threading
import time
from typing import Callable

import pandas as pd

from .client import public_get
from .config import Config, load
from .tables import build_history, build_orderbook, build_trades, to_columns

CACHE_SECONDS = 20   # Tableau may run a script more than once per refresh

_cache: dict[tuple, tuple[float, dict]] = {}
_lock = threading.Lock()


def _cached(name: str, cfg: Config, build: Callable[[Config], pd.DataFrame]) -> dict[str, list]:
    key = (name, cfg)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    result = to_columns(build(cfg))
    with _lock:
        _cache[key] = (time.time(), result)
    return result


def history(ticker: str | None = None) -> dict[str, list]:
    """Candles (1d/1h/optional 1m) plus a live row per market, with every current market field on each row."""
    return _cached("history", load(ticker), lambda cfg: build_history(cfg, public_get))


def orderbook(ticker: str | None = None) -> dict[str, list]:
    """Current order book, one row per price level (YES terms). Kalshi keeps no book history."""
    return _cached("orderbook", load(ticker), lambda cfg: build_orderbook(cfg, public_get))


def trades(ticker: str | None = None) -> dict[str, list]:
    """Individual executions within KXTAB_TRADES_DAYS."""
    return _cached("trades", load(ticker), lambda cfg: build_trades(cfg, public_get))


__all__ = ["history", "orderbook", "trades"]
