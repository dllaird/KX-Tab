"""Live smoke tests against Kalshi's public API. Opt in: set KXTAB_LIVE_TESTS=1."""
from __future__ import annotations

import os

import pytest

from kxtab import tables
from kxtab.client import public_get
from kxtab.config import Config

pytestmark = pytest.mark.skipif(os.environ.get("KXTAB_LIVE_TESTS") != "1", reason="set KXTAB_LIVE_TESTS=1")


@pytest.mark.parametrize("ticker", ["KXNCAAF-27-TEX", "KXMLBPLAYOFFS-25-PIT"])
def test_history_live(ticker):
    df = tables.build_history(Config(tickers=(ticker,), daily_days=30, hourly_days=1), public_get)
    assert len(df) > 0 and df["is_live"].sum() == 2
    assert df.loc[df["is_live"], "market_ticker"].eq(ticker).all()


def test_orderbook_and_trades_live():
    cfg = Config(tickers=("KXNCAAF-27-TEX",), trades_days=1, max_trades=50)
    assert set(tables.build_orderbook(cfg, public_get)["side"]) <= {"bid", "ask"}
    assert len(tables.build_trades(cfg, public_get)) <= 50
