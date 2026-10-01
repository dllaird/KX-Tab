"""Offline fake of Kalshi's public API, served from recorded (trimmed) real responses."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kxtab.client import NotFound  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
ARCHIVED = "KXMLBNLCENT-25-PIT"


def load(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


META = load("meta")
NOW = META["recorded_ts"]


class FakeKalshi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.live = {m["ticker"]: m for m in load("event_KXNCAAF-27")["event"]["markets"]}
        self.hist = {m["ticker"]: m for m in load("hist_markets_KXMLBPLAYOFFS-25")["markets"]}
        self.hist[ARCHIVED] = load(f"hist_market_{ARCHIVED}")["market"]
        self.events = {e: load(f"event_{e}") for e in ("KXNCAAF-27", "KXMLBNLCENT-25", "KXMLBPLAYOFFS-25")}
        self.series = {s: load(f"series_{s}") for s in ("KXNCAAF", "KXMLBNLCENT", "KXMLBPLAYOFFS")}

    def __call__(self, path: str, params: dict | None = None) -> dict:
        params = params or {}
        self.calls.append((path, params))
        parts = path.strip("/").split("/")
        if path == "/markets/candlesticks":
            data = load(f"candles_live_{params['period_interval']}")
            wanted = set(params["market_tickers"].split(","))
            return {"markets": [e for e in data["markets"] if e["market_ticker"] in wanted]}
        if path == "/markets/trades":
            return load("trades_page2_KXNCAAF-27-TEX" if params.get("cursor") else "trades_page1_KXNCAAF-27-TEX")
        if path == "/historical/trades":
            return load(f"hist_trades_{ARCHIVED}")
        if path == "/historical/markets":
            if params.get("event_ticker") == "KXMLBPLAYOFFS-25" or params.get("series_ticker") == "KXMLBPLAYOFFS":
                return load("hist_markets_KXMLBPLAYOFFS-25")
            return {"markets": [], "cursor": ""}
        if path == "/events":
            if params.get("series_ticker") == "KXNCAAF":
                return load("events_series_KXNCAAF_open")
            return {"events": [], "cursor": ""}
        if parts[0] == "markets" and len(parts) == 3 and parts[2] == "orderbook":
            return load(f"orderbook_{parts[1]}")
        if parts[0] == "markets" and len(parts) == 2 and parts[1] in self.live:
            return {"market": self.live[parts[1]]}
        if parts[:2] == ["historical", "markets"] and len(parts) == 4 and parts[3] == "candlesticks":
            return load(f"candles_hist_{params['period_interval']}")
        if parts[:2] == ["historical", "markets"] and len(parts) == 3 and parts[2] in self.hist:
            return {"market": self.hist[parts[2]]}
        if parts[0] == "events" and len(parts) == 2 and parts[1] in self.events:
            return self.events[parts[1]]
        if parts[0] == "series" and len(parts) == 2 and parts[1] in self.series:
            return self.series[parts[1]]
        raise NotFound(path)


@pytest.fixture
def fake() -> FakeKalshi:
    return FakeKalshi()
