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
- `kxtab.history("TICKER")` overrides `KXTAB_TICKER` for that call (useful on a shared server).
- Preview without Tableau: `python -m kxtab --ticker KXNCAAF-27 --table history --csv out.csv`.
- Tests: `pytest` (offline); `KXTAB_LIVE_TESTS=1 pytest` adds live API checks.

## Running on a server (Tableau Cloud)

Tableau Cloud calls TabPy over the internet, so the server needs HTTPS with a certificate from a public
CA that matches its DNS name (e.g. an Azure VM DNS label, `<name>.<region>.cloudapp.azure.com`).
Use `deploy/tabpy-https.conf` and settings from `deploy/kxtab.env.example`.

**Network:** open inbound TCP 9004 only to your Tableau Cloud pod's IP ranges (Tableau's "Tableau Cloud
IP addresses" list) in the Azure NSG and the OS firewall. Certbot's standalone challenge also needs
TCP 80 during issuance and renewal.

**Linux VM** (repo at `/opt/KX-Tab`):
```bash
sudo useradd --system --home /opt/KX-Tab kxtab
sudo git clone https://github.com/dllaird/KX-Tab.git /opt/KX-Tab && cd /opt/KX-Tab
sudo python3 -m venv .venv && sudo .venv/bin/pip install -r requirements.txt -r requirements-tabpy.txt
sudo chown -R kxtab:kxtab /opt/KX-Tab && sudo chmod +x deploy/linux/*.sh
sudo mkdir -p /etc/kxtab && sudo cp deploy/kxtab.env.example /etc/kxtab/kxtab.env    # edit it
sudo .venv/bin/tabpy-user add -u tableau -p <password> -f /etc/kxtab/tabpy_users.txt
sudo chown root:kxtab /etc/kxtab/tabpy_users.txt && sudo chmod 640 /etc/kxtab/tabpy_users.txt
sudo certbot certonly --standalone -d <dns-name> \
  --deploy-hook /opt/KX-Tab/deploy/linux/certbot-deploy-hook.sh                      # copies certs to /etc/kxtab/tls
sudo cp deploy/linux/kxtab-tabpy.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now kxtab-tabpy             # logs: journalctl -u kxtab-tabpy
```

**Windows VM:** install requirements as above, create the TabPy user, put PEM cert/key files on disk
(e.g. win-acme with PEM output), fill in a `kxtab.env`, then as Administrator:
```powershell
.\deploy\windows\register_task.ps1 -EnvFile C:\kxtab\kxtab.env -AllowFrom <tableau-cloud-ip-ranges>
Start-ScheduledTask -TaskName "KX-Tab TabPy"
```

**Tableau Cloud:** Settings > Extensions > Analytics Extensions: enable, add a TabPy connection with
host `<dns-name>`, port 9004, SSL on, and the TabPy username/password. Table extensions in workbooks
then run on the server. When several workbooks share one server, pass the ticker in the script:
`return kxtab.history("KXNCAAF-27")`.

## License

MIT. See [LICENSE](LICENSE).
