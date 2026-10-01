"""KX-Tab tests (offline, recorded fixtures)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import kxtab
from kxtab import config, derive, normalize, tables
from kxtab.config import Config, ConfigError
from kxtab.resolve import ResolveError, resolve

from conftest import ARCHIVED, NOW, load

EVENT, MARKET = "KXNCAAF-27", "KXNCAAF-27-TEX"


def cfg(ticker: str, **kw) -> Config:
    return Config(tickers=tuple(t.strip() for t in ticker.split(",")), **kw)


# --- config ------------------------------------------------------------------------------------
def test_config_requires_ticker(monkeypatch):
    monkeypatch.delenv("KXTAB_TICKER", raising=False)
    with pytest.raises(ConfigError, match="KXTAB_TICKER"):
        config.load()


def test_config_parses_env(monkeypatch):
    monkeypatch.setenv("KXTAB_TICKER", " kxncaaf-27 , KXNCAAF-27-TEX,kxncaaf-27 ")
    monkeypatch.setenv("KXTAB_HOURLY_DAYS", "3")
    c = config.load()
    assert c.tickers == ("KXNCAAF-27", "KXNCAAF-27-TEX") and c.hourly_days == 3 and c.daily_days == 400
    monkeypatch.setenv("KXTAB_SERIES_STATUS", "closed")
    with pytest.raises(ConfigError):
        config.load()
    monkeypatch.setenv("KXTAB_SERIES_STATUS", "all")
    monkeypatch.setenv("KXTAB_MAX_MARKETS", "lots")
    with pytest.raises(ConfigError, match="KXTAB_MAX_MARKETS"):
        config.load()


# --- resolve -----------------------------------------------------------------------------------
def test_resolve_event(fake):
    s = resolve(fake, (EVENT,))
    assert {m.ticker for m in s.markets} == {"KXNCAAF-27-TEX", "KXNCAAF-27-UGA", "KXNCAAF-27-VAN"}
    assert not any(m.historical for m in s.markets) and "KXNCAAF" in s.series


def test_resolve_market_fetches_event_and_series(fake):
    s = resolve(fake, (MARKET,))
    assert [m.ticker for m in s.markets] == [MARKET]
    assert s.events[EVENT]["mutually_exclusive"] is True and s.series["KXNCAAF"]["title"]


def test_resolve_archived_market(fake):
    s = resolve(fake, (ARCHIVED,))
    assert s.markets[0].historical and s.markets[0].raw["result"] == "no"


def test_resolve_settled_event_uses_historical_markets(fake):
    s = resolve(fake, ("KXMLBPLAYOFFS-25",))
    assert {m.ticker for m in s.markets} == {"KXMLBPLAYOFFS-25-PIT", "KXMLBPLAYOFFS-25-LAD"}
    assert all(m.historical for m in s.markets)


def test_resolve_series(fake):
    s = resolve(fake, ("KXNCAAF",))
    assert {m.ticker for m in s.markets} == {"KXNCAAF-27-TEX", "KXNCAAF-27-UGA", "KXNCAAF-27-VAN"}


def test_resolve_list_dedup_unknown_and_cap(fake):
    s = resolve(fake, (MARKET, EVENT))
    assert len(s.markets) == 3
    with pytest.raises(ResolveError, match="not found"):
        resolve(fake, ("NOPE",))
    with pytest.raises(ResolveError, match="KXTAB_MAX_MARKETS"):
        resolve(fake, (EVENT,), max_markets=2)


# --- normalize / derive ----------------------------------------------------------------------
def test_flatten_market():
    f = normalize.flatten(load("event_KXNCAAF-27")["event"]["markets"][0])
    assert not any(k.endswith(("_dollars", "_fp")) for k in f)
    assert isinstance(f["yes_bid"], float) and isinstance(f["volume"], float)
    assert len(f["close_time"]) == 19 and f["close_time"][4] == "-"
    assert isinstance(f["price_ranges"], str) and f["price_ranges"].startswith("[")


def test_live_and_historical_candles_share_columns():
    live = normalize.candle(load("candles_live_1440")["markets"][0]["candlesticks"][-1])
    hist = normalize.candle(load("candles_hist_1440")["candlesticks"][-1])
    assert set(live) == set(hist)
    assert all(v is None or isinstance(v, float) for k, v in hist.items() if k != "time_utc")


def test_mid_rules():
    assert derive.mid(0.12, 0.14) == 0.13
    assert derive.mid(0.0, 0.07) == 0.035            # one-sided: half the ask, as in the dashboard
    assert derive.mid(0.0, 1.0, 0.04) == 0.04        # empty book -> last trade
    assert derive.mid(None, None, None) is None
    assert derive.spread(0.12, 0.14) == 0.02 and derive.spread(None, 0.1) is None
    q = derive.devig_power([0.5, 0.3, 0.3])
    assert q.sum() == pytest.approx(1) and q[0] > q[1]


# --- history --------------------------------------------------------------------------------------
@pytest.fixture
def hist(fake) -> pd.DataFrame:
    return tables.build_history(cfg(EVENT), fake, now=NOW)


def test_history_live_rows_and_current_filter(hist):
    live = hist[hist["is_live"]]
    assert set(hist["resolution"]) == {"1d", "1h"}
    assert len(live) == 3 * 2                                        # one per market per resolution
    current = hist[hist["is_live"] & (hist["resolution"] == "1d")]
    assert current["market_ticker"].is_unique and len(current) == 3
    for _, g in hist.groupby(["market_ticker", "resolution"]):
        assert g["time_utc"].is_monotonic_increasing and g["is_live"].iloc[-1]


def test_history_numeric_columns_are_numeric(hist):
    for col in tables.CANDLE_COLUMNS + ["market_yes_bid", "market_yes_ask", "market_volume", "market_volume_24h",
                                        "market_mid", "market_fair_probability"]:
        vals = hist[col].dropna()
        assert all(isinstance(v, (int, float, np.integer, np.floating)) for v in vals), col


def test_history_text_fields_only_on_live_rows(hist):
    past = hist[~hist["is_live"]]
    assert past["market_title"].isna().all() and past["market_rules_primary"].isna().all()
    assert past["market_status"].notna().all()                       # kept for filtering
    assert hist.loc[hist["is_live"], "market_title"].notna().all()


def test_history_devig_only_for_mutually_exclusive(fake, hist):
    cur = hist[hist["is_live"] & (hist["resolution"] == "1d")]
    assert cur["market_fair_probability"].sum() == pytest.approx(1)
    settled = tables.build_history(cfg("KXMLBPLAYOFFS-25"), fake, now=NOW)
    assert settled["market_fair_probability"].isna().all()           # playoff qualifiers aren't exclusive


def test_history_archived_market(fake):
    df = tables.build_history(cfg(ARCHIVED), fake, now=NOW)
    assert df["is_historical"].all() and len(df[~df["is_live"]]) > 0
    assert any(p.startswith(f"/historical/markets/{ARCHIVED}/candlesticks") for p, _ in fake.calls)
    close = normalize.to_utc(load(f"hist_market_{ARCHIVED}")["market"]["close_time"])
    for _, g in df.groupby("resolution"):                                 # closed market: live row is last, at/after close
        assert g["is_live"].iloc[-1] and g["time_utc"].iloc[-1] == g["time_utc"].max() >= close
    assert df["time_utc"].max() < "2025-10-01"                            # windows end at close, not today


def test_history_is_json_safe(hist):
    out = tables.to_columns(hist)
    text = json.dumps(out)
    assert "NaN" not in text and len({len(v) for v in out.values()}) == 1


# --- orderbook / trades -----------------------------------------------------------------------
def test_orderbook_yes_terms_best_first(fake):
    ob = tables.build_orderbook(cfg(EVENT), fake, now=NOW)
    raw = load(f"orderbook_{MARKET}")["orderbook_fp"]
    tex = ob[ob["market_ticker"] == MARKET]
    bids, asks = tex[tex["side"] == "bid"], tex[tex["side"] == "ask"]
    assert bids["price"].iloc[0] == max(float(p) for p, _ in raw["yes_dollars"])
    assert asks["price"].iloc[0] == pytest.approx(1 - max(float(p) for p, _ in raw["no_dollars"]))
    assert bids["price"].is_monotonic_decreasing and asks["price"].is_monotonic_increasing
    assert (asks["raw_side"] == "no").all() and list(bids["level"]) == list(range(1, len(bids) + 1))
    assert len(tables.build_orderbook(cfg(ARCHIVED), fake, now=NOW)) == 0   # no book history


def test_trades_paginate_and_cap(fake):
    tr = tables.build_trades(cfg(MARKET), fake, now=NOW)
    assert len(tr) == 5                                                 # 3 + 2 across two pages
    assert tr["time_utc"].is_monotonic_decreasing and tr["count"].map(type).eq(float).all()
    assert len(tables.build_trades(cfg(MARKET, max_trades=2), fake, now=NOW)) == 2
    arch = tables.build_trades(cfg(ARCHIVED), fake, now=NOW)
    assert len(arch) == 3 and any(p == "/historical/trades" for p, _ in fake.calls)


# --- public API ----------------------------------------------------------------------------------
def test_public_functions_read_env_and_cache(fake, monkeypatch):
    monkeypatch.setenv("KXTAB_TICKER", EVENT)
    monkeypatch.setattr(kxtab, "public_get", fake)
    monkeypatch.setattr(kxtab, "_cache", {})
    out = kxtab.history()
    n_calls = len(fake.calls)
    assert set(out) >= {"market_ticker", "time_utc", "mid", "market_mid"} and json.dumps(out)
    assert kxtab.history() is out and len(fake.calls) == n_calls        # cached within CACHE_SECONDS
    assert set(kxtab.orderbook()) >= {"side", "price"} and set(kxtab.trades()) >= {"trade_id"}
