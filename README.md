# KX-Tab

Kalshi market data in Tableau via TabPy table extensions. Set a ticker; get live and historical data
for every market under it. Uses Kalshi's public API (no key).

## Setup

KX-Tab runs inside any TabPy whose Python has `requests`, `pandas` and `numpy`; it only needs to be
on TabPy's `PYTHONPATH`. To install TabPy here too: `pip install -r requirements-tabpy.txt`.

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
tabpy-user add -u tableau -p <password> -f tableau\tabpy_users.txt
.\tableau\start_tabpy.ps1 -Ticker KXNCAAF-27 [-TabPy C:\path\to\tabpy.exe]   # or: setx KXTAB_TICKER KXNCAAF-27
```

The launcher uses `-TabPy`, else `KXTAB_TABPY`, else `.venv\Scripts\tabpy.exe`, else `tabpy` on PATH,
and requires a TabPy login (port 9004, settings in `tableau\tabpy.conf`).

Connect Tableau's analytics extension to `localhost:9004` with that user, then create table extensions:

```python
import kxtab
return kxtab.history()      # or kxtab.orderbook() / kxtab.trades()
```

`KXTAB_TICKER` takes a series (`KXNCAAF`), event (`KXNCAAF-27`) or market (`KXNCAAF-27-TEX`),
comma-separated for several. Settled/archived markets work too. TabPy reads env vars at startup:
restart it after changing them.

## Settings

| Variable | Default | |
|---|---|---|
| `KXTAB_TICKER` | required | series / event / market ticker(s) |
| `KXTAB_SERIES_STATUS` | `open` | series tickers: `open` events or `all` (incl. settled) |
| `KXTAB_DAILY_DAYS` | `400` | daily candles lookback |
| `KXTAB_HOURLY_DAYS` | `8` | hourly candles lookback |
| `KXTAB_MINUTE_HOURS` | `0` | 1-minute candles lookback (off by default) |
| `KXTAB_TRADES_DAYS` | `7` | trades lookback |
| `KXTAB_MAX_MARKETS` | `300` | error if a ticker covers more markets |
| `KXTAB_MAX_TRADES` | `200000` | trade row cap |

## Tables

**`history()`**: one row per market × resolution (`1d`, `1h`, `1m`) × candle, plus one `is_live` row per
market and resolution with current values.
- identity: `series_*`, `event_*`, `market_ticker`, `label`, `is_historical`
- candle: `time_utc`, `yes_bid_*`, `yes_ask_*`, `price_*` (open/high/low/close, mean, previous), `volume`, `open_interest`, `mid`, `spread`
- current market fields (`market_*`): every field Kalshi returns, plus `market_mid`, `market_spread`, `market_fair_probability` (power de-vig, mutually exclusive events only). Text fields are on live rows only.

**`orderbook()`**: current resting levels, in YES terms (`side` bid/ask, `level` 1 = best, `price`, `contracts`, `cumulative_contracts`).

**`trades()`**: executions (`time_utc`, `yes_price`, `no_price`, `count`, `taker_side`, …), newest first.

## Notes

- `time_utc` is text (JSON has no dates): use `DATETIME([time_utc])`.
- Current values: filter `is_live` = True and `resolution` = `1d` (one row per market).
- If a numeric field lands under dimensions, use Convert to Measure.
- Kalshi keeps no order-book history; `orderbook()` is a snapshot, empty for archived markets.
- Archived markets are fetched one at a time and are slower (~0.5 s per market).
- Preview without Tableau: `python -m kxtab --ticker KXNCAAF-27 --table history --csv out.csv`.
- Tests: `pytest` (offline); `KXTAB_LIVE_TESTS=1 pytest` adds live API checks.
