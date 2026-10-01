"""Table builders: history (main), orderbook, trades."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
import pandas as pd

from . import derive
from .client import Getter, pages
from .config import Config
from .normalize import candle, flatten, to_utc
from .resolve import MarketRef, Scope, resolve

CANDLE_BUDGET = 5_000     # max candle periods per request (tickers x periods)
LIVE_TICKERS = 25         # max tickers per live candlestick request
WORKERS = 4               # parallel per-market requests (client paces them)
KEEP_TEXT = {"market_ticker", "market_status", "market_result"}   # text market fields kept on every history row
CANDLE_COLUMNS = [f"{g}_{k}" for g in ("yes_bid", "yes_ask") for k in ("open", "high", "low", "close")] + \
    [f"price_{k}" for k in ("open", "high", "low", "close", "mean", "previous")] + \
    ["volume", "open_interest", "mid", "spread"]


def _now_ts(now: float | None) -> int:
    return int(time.time() if now is None else now)


def _ts(value: Any) -> int | None:
    s = to_utc(value)
    return None if s is None else int(pd.Timestamp(s, tz="UTC").timestamp())


def _end_ts(m: MarketRef, now: int) -> int:
    """Windows end now, or at close for markets that already closed."""
    close = _ts(m.raw.get("close_time"))
    return min(now, close) if close else now


def identity(scope: Scope, m: MarketRef) -> dict[str, Any]:
    event = scope.events.get(m.event_ticker, {})
    series = scope.series_of(m)
    return {
        "series_ticker": event.get("series_ticker") or series.get("ticker"),
        "series_title": series.get("title"),
        "series_category": series.get("category"),
        "event_ticker": m.event_ticker,
        "event_title": event.get("title"),
        "event_sub_title": event.get("sub_title"),
        "event_mutually_exclusive": event.get("mutually_exclusive"),
        "market_ticker": m.ticker,
        "label": m.raw.get("yes_sub_title") or m.raw.get("title") or m.ticker,
        "is_historical": m.historical,
    }


# --- history -------------------------------------------------------------------------------
def _resolutions(cfg: Config) -> list[tuple[str, int, int]]:
    """(name, period minutes, window seconds) for each enabled resolution."""
    out = [("1d", 1440, int(cfg.daily_days * 86400)), ("1h", 60, int(cfg.hourly_days * 86400)),
           ("1m", 1, int(cfg.minute_hours * 3600))]
    return [r for r in out if r[2] > 0]


def _time_chunks(start: int, end: int, period_s: int, per_ticker_budget: int) -> list[tuple[int, int]]:
    step = max(period_s, per_ticker_budget * period_s)
    return [(lo, min(lo + step, end)) for lo in range(start, end, step)]


def _fetch_candles(get: Getter, markets: list[MarketRef], resolution: tuple[str, int, int],
                   now: int) -> dict[str, list[dict]]:
    """market ticker -> raw candles for one resolution."""
    _, period, window = resolution
    period_s = period * 60
    out: dict[str, list[dict]] = {m.ticker: [] for m in markets}
    live = [m for m in markets if not m.historical]
    archived = [m for m in markets if m.historical]

    # Live markets: batch by shared window end (open markets share "now").
    groups: dict[int, list[MarketRef]] = {}
    for m in live:
        groups.setdefault(_end_ts(m, now), []).append(m)
    for end, group in groups.items():
        start = end - window
        periods = max(1, window // period_s)
        per_request = max(1, min(LIVE_TICKERS, CANDLE_BUDGET // periods))
        for lo, hi in _time_chunks(start, end, period_s, CANDLE_BUDGET):
            for i in range(0, len(group), per_request):
                tickers = [m.ticker for m in group[i:i + per_request]]
                data = get("/markets/candlesticks", {"market_tickers": ",".join(tickers), "start_ts": lo,
                                                     "end_ts": hi, "period_interval": period})
                for entry in data.get("markets") or []:
                    out.setdefault(entry["market_ticker"], []).extend(entry.get("candlesticks") or [])

    def one(m: MarketRef) -> tuple[str, list[dict]]:
        end = _end_ts(m, now)
        candles = []
        for lo, hi in _time_chunks(end - window, end, period_s, CANDLE_BUDGET):
            candles += get(f"/historical/markets/{m.ticker}/candlesticks",
                           {"start_ts": lo, "end_ts": hi, "period_interval": period}).get("candlesticks") or []
        return m.ticker, candles

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for ticker, candles in pool.map(one, archived):
            out[ticker] = candles
    return out


def _snapshot(scope: Scope) -> pd.DataFrame:
    """Current market fields (prefixed market_) plus derived mid, spread and de-vigged probability."""
    rows = []
    for m in scope.markets:
        f = flatten(m.raw)
        row = {"market_ticker": m.ticker, **{f"market_{k}": v for k, v in f.items() if k != "ticker"}}
        row["market_mid"] = derive.mid(f.get("yes_bid"), f.get("yes_ask"), f.get("last_price"))
        row["market_spread"] = derive.spread(f.get("yes_bid"), f.get("yes_ask"))
        rows.append(row)
    snap = pd.DataFrame(rows)
    snap["market_fair_probability"] = np.nan
    for event_ticker, event in scope.events.items():
        if not event.get("mutually_exclusive"):
            continue
        tickers = {m.ticker for m in scope.markets if m.event_ticker == event_ticker}
        sel = snap["market_ticker"].isin(tickers) & (snap["market_mid"].fillna(0) > 0)
        if sel.sum() > 1:
            snap.loc[sel, "market_fair_probability"] = derive.devig_power(snap.loc[sel, "market_mid"].to_numpy())
    return snap


def build_history(cfg: Config, get: Getter, now: float | None = None) -> pd.DataFrame:
    now_ts = _now_ts(now)
    scope = resolve(get, cfg.tickers, cfg.series_status, cfg.max_markets)
    snap = _snapshot(scope).set_index("market_ticker")
    rows = []
    for res in _resolutions(cfg):
        candles = _fetch_candles(get, scope.markets, res, now_ts)
        for m in scope.markets:
            ident = identity(scope, m)
            # Live row goes last: at now (or close), but never before the final candle's period end.
            live_ts = max([_end_ts(m, now_ts)] + [int(c["end_period_ts"]) for c in candles.get(m.ticker, [])])
            for c in candles.get(m.ticker, []):
                row = {**ident, "resolution": res[0], "is_live": False, **candle(c)}
                last = row.get("price_close") or row.get("price_previous")
                row["mid"] = derive.mid(row.get("yes_bid_close"), row.get("yes_ask_close"), last)
                row["spread"] = derive.spread(row.get("yes_bid_close"), row.get("yes_ask_close"))
                rows.append(row)
            s = snap.loc[m.ticker]
            rows.append({**ident, "resolution": res[0], "is_live": True, "time_utc": to_utc(live_ts),
                         "yes_bid_close": s.get("market_yes_bid"), "yes_ask_close": s.get("market_yes_ask"),
                         "price_close": s.get("market_last_price"), "open_interest": s.get("market_open_interest"),
                         "mid": s.get("market_mid"), "spread": s.get("market_spread")})
    df = pd.DataFrame(rows)
    df = df.drop_duplicates(["market_ticker", "resolution", "time_utc", "is_live"], keep="last")
    df = df.join(snap, on="market_ticker")
    # Text market fields (titles, rules, times, ids) only on live rows; numbers stay on every row. Keeps the payload small.
    history_rows = ~df["is_live"].astype(bool)
    for col in df.columns:
        if col.startswith("market_") and col not in KEEP_TEXT and df[col].map(lambda v: isinstance(v, str)).any():
            df.loc[history_rows, col] = None
    lead = list(identity(scope, scope.markets[0])) + ["resolution", "time_utc", "is_live"]
    candle_cols = [c for c in CANDLE_COLUMNS if c in df.columns]
    market_cols = [c for c in df.columns if c.startswith("market_") and c not in lead]
    return df[lead + candle_cols + market_cols].sort_values(
        ["market_ticker", "resolution", "time_utc"]).reset_index(drop=True)


# --- orderbook -----------------------------------------------------------------------------
def build_orderbook(cfg: Config, get: Getter, now: float | None = None) -> pd.DataFrame:
    scope = resolve(get, cfg.tickers, cfg.series_status, cfg.max_markets)
    snapshot = to_utc(_now_ts(now))
    live = [m for m in scope.markets if not m.historical]

    def one(m: MarketRef) -> list[dict]:
        book = get(f"/markets/{m.ticker}/orderbook").get("orderbook_fp") or {}
        ident, rows = identity(scope, m), []
        for side, key, raw_side, to_yes in (("bid", "yes_dollars", "yes", lambda p: p),
                                            ("ask", "no_dollars", "no", lambda p: 1 - p)):
            levels = [(to_yes(float(p)), float(q)) for p, q in book.get(key) or []]
            levels.sort(key=lambda x: -x[0] if side == "bid" else x[0])   # best first
            cum = 0.0
            for level, (price, qty) in enumerate(levels, 1):
                cum += qty
                rows.append({**ident, "snapshot_utc": snapshot, "side": side, "raw_side": raw_side, "level": level,
                             "price": round(price, 4), "contracts": qty, "cumulative_contracts": round(cum, 2),
                             "notional": round(price * qty, 2)})
        return rows

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        rows = [r for part in pool.map(one, live) for r in part]
    cols = list(identity(scope, scope.markets[0])) + ["snapshot_utc", "side", "raw_side", "level", "price",
                                                      "contracts", "cumulative_contracts", "notional"]
    return pd.DataFrame(rows, columns=cols)


# --- trades --------------------------------------------------------------------------------
def build_trades(cfg: Config, get: Getter, now: float | None = None) -> pd.DataFrame:
    now_ts = _now_ts(now)
    scope = resolve(get, cfg.tickers, cfg.series_status, cfg.max_markets)
    window = int(cfg.trades_days * 86400)

    def one(m: MarketRef) -> list[dict]:
        end = _end_ts(m, now_ts)
        path = "/historical/trades" if m.historical else "/markets/trades"
        ident, rows = identity(scope, m), []
        for t in pages(get, path, {"ticker": m.ticker, "min_ts": end - window}, "trades", max_items=cfg.max_trades):
            f = flatten(t)
            rows.append({**ident, "trade_id": f.get("trade_id"), "time_utc": f.get("created_time"),
                         "yes_price": f.get("yes_price"), "no_price": f.get("no_price"), "count": f.get("count"),
                         "taker_side": f.get("taker_side"), "taker_book_side": f.get("taker_book_side"),
                         "taker_outcome_side": f.get("taker_outcome_side"), "is_block_trade": f.get("is_block_trade")})
        return rows

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        rows = [r for part in pool.map(one, scope.markets) for r in part]
    rows.sort(key=lambda r: r["time_utc"] or "", reverse=True)
    cols = list(identity(scope, scope.markets[0])) + ["trade_id", "time_utc", "yes_price", "no_price", "count",
                                                      "taker_side", "taker_book_side", "taker_outcome_side",
                                                      "is_block_trade"]
    return pd.DataFrame(rows[: cfg.max_trades], columns=cols)


# --- Tableau output -------------------------------------------------------------------------
def to_columns(df: pd.DataFrame) -> dict[str, list]:
    """DataFrame -> {column: list} with plain Python values and None for missing (JSON-safe)."""
    def plain(v):
        if v is None or v is pd.NA or (isinstance(v, float) and np.isnan(v)):
            return None
        return v.item() if isinstance(v, np.generic) else v
    return {c: [plain(v) for v in df[c].tolist()] for c in df.columns}

