"""Turn ticker(s) into the markets they cover (series, event or market; live or archived)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .client import Getter, NotFound, pages


@dataclass
class MarketRef:
    ticker: str
    event_ticker: str
    historical: bool          # served by /historical endpoints (archived after settlement)
    raw: dict


@dataclass
class Scope:
    markets: list[MarketRef] = field(default_factory=list)
    events: dict[str, dict] = field(default_factory=dict)   # event_ticker -> event fields
    series: dict[str, dict] = field(default_factory=dict)   # series_ticker -> series fields

    def series_of(self, m: MarketRef) -> dict:
        return self.series.get(self.events.get(m.event_ticker, {}).get("series_ticker", ""), {})


class ResolveError(ValueError):
    pass


def _try(get: Getter, path: str, params: dict | None = None) -> dict | None:
    try:
        return get(path, params)
    except NotFound:
        return None


def _event_markets(get: Getter, event_ticker: str, data: dict) -> list[MarketRef]:
    # Recent events nest markets under "event"; older ones return them top-level or only in /historical.
    raw = (data.get("event") or {}).get("markets") or data.get("markets") or []
    if raw:
        return [MarketRef(m["ticker"], m.get("event_ticker") or event_ticker, False, m) for m in raw]
    return [MarketRef(m["ticker"], m.get("event_ticker") or event_ticker, True, m)
            for m in pages(get, "/historical/markets", {"event_ticker": event_ticker}, "markets")]


def _resolve_token(get: Getter, token: str, series_status: str, scope: Scope) -> list[MarketRef]:
    data = _try(get, f"/markets/{token}")
    if data:
        return [MarketRef(token, data["market"]["event_ticker"], False, data["market"])]
    data = _try(get, f"/historical/markets/{token}")
    if data:
        return [MarketRef(token, data["market"]["event_ticker"], True, data["market"])]

    data = _try(get, f"/events/{token}", {"with_nested_markets": "true"})
    if data:
        scope.events[token] = _event_fields(data)
        return _event_markets(get, token, data)

    data = _try(get, f"/series/{token}")
    if data:
        scope.series[token] = data["series"]
        params = {"series_ticker": token, "with_nested_markets": "true"}
        if series_status == "open":
            params["status"] = "open"
        found: list[MarketRef] = []
        for event in pages(get, "/events", params, "events", limit=200):
            scope.events[event["event_ticker"]] = _event_fields({"event": event})
            found += [MarketRef(m["ticker"], event["event_ticker"], False, m) for m in event.get("markets") or []]
        if series_status == "all":
            live = {m.ticker for m in found}
            found += [MarketRef(m["ticker"], m["event_ticker"], True, m)
                      for m in pages(get, "/historical/markets", {"series_ticker": token}, "markets")
                      if m["ticker"] not in live]
        return found

    raise ResolveError(f"Ticker '{token}' not found as a Kalshi market, event or series.")


def _event_fields(data: dict) -> dict:
    return {k: v for k, v in (data.get("event") or {}).items() if k != "markets"}


def resolve(get: Getter, tickers: tuple[str, ...], series_status: str = "open", max_markets: int = 300) -> Scope:
    scope = Scope()
    seen: dict[str, MarketRef] = {}
    for token in tickers:
        for m in _resolve_token(get, token, series_status, scope):
            if m.ticker not in seen or (seen[m.ticker].historical and not m.historical):
                seen[m.ticker] = m
            if len(seen) > max_markets:
                raise ResolveError(f"{', '.join(tickers)} covers more than KXTAB_MAX_MARKETS={max_markets} markets. "
                                   "Use a narrower ticker or raise the limit.")
    scope.markets = list(seen.values())
    if not scope.markets:
        raise ResolveError(f"No markets found for {', '.join(tickers)}.")
    for m in scope.markets:
        if m.event_ticker not in scope.events:
            data = _try(get, f"/events/{m.event_ticker}")
            scope.events[m.event_ticker] = _event_fields(data) if data else {"event_ticker": m.event_ticker}
    for event in scope.events.values():
        s = event.get("series_ticker")
        if s and s not in scope.series:
            data = _try(get, f"/series/{s}")
            scope.series[s] = data["series"] if data else {"ticker": s}
    return scope
