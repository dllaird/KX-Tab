# KX-Tab

Kalshi market data in Tableau via TabPy table extensions. Set a ticker; get live and historical data
for every market under it. Uses Kalshi's public API (no key).

## Setup

KX-Tab runs inside any TabPy whose Python has `requests`, `pandas` and `numpy`; it only needs to be
on TabPy's `PYTHONPATH`. To install TabPy here too: `pip install -r requirements-tabpy.txt`.

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
python -m tabpy.utils.tabpy_user add -u tableau -p <password> -f tableau\tabpy_users.txt   # TabPy's python
.\tableau\start_tabpy.ps1 -Ticker KXNCAAF-27 [-TabPy C:\path\to\tabpy.exe]   # or: setx KXTAB_TICKER KXNCAAF-27
```

The launcher uses `-TabPy`, else `KXTAB_TABPY`, else `.venv\Scripts\tabpy.exe`, else `tabpy` on PATH,
and requires a TabPy login (port 9004, settings in `tableau\tabpy.conf`). It runs that environment's
`python.exe -m tabpy.tabpy` rather than `tabpy.exe`, since Windows Application Control may block pip's
`.exe` launchers; `-TabPy` also accepts a `python.exe` directly.

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

**Azure App Service** (Linux, Python; B1 or higher for Always On). App Service terminates HTTPS on 443
with its own certificate, so no certbot or cert files. TabPy listens on HTTP 8000 behind it
(`deploy/appservice/tabpy.conf`), and `deploy/appservice/startup.sh` writes the TabPy login from app
settings at each start. From Azure Cloud Shell (bash):
```bash
RG=kxtab-rg; APP=<globally-unique-name>; LOC=eastus
az group create -n $RG -l $LOC
az appservice plan create -g $RG -n kxtab-plan --is-linux --sku B1
az webapp create -g $RG -p kxtab-plan -n $APP --runtime "PYTHON:3.12" \
  --startup-file "bash deploy/appservice/startup.sh"
az webapp config appsettings set -g $RG -n $APP --settings \
  KXTAB_TICKER=KXNCAAF-27 KXTAB_TABPY_PASSWORD='<password>' WEBSITES_PORT=8000 \
  SCM_DO_BUILD_DURING_DEPLOYMENT=true PRE_BUILD_COMMAND="cat requirements-tabpy.txt >> requirements.txt"
az webapp config set -g $RG -n $APP --always-on true --ftps-state Disabled
az webapp update -g $RG -n $APP --https-only true
az webapp log config -g $RG -n $APP --docker-container-logging filesystem
git clone https://github.com/dllaird/KX-Tab.git && cd KX-Tab && git archive -o kxtab.zip HEAD
az webapp deploy -g $RG -n $APP --src-path kxtab.zip --type zip                      # logs: az webapp log tail -g $RG -n $APP
curl -u tableau:'<password>' https://$APP.azurewebsites.net/info                      # expect JSON, not 401
az webapp config access-restriction add -g $RG -n $APP --rule-name tableau-cloud \
  --action Allow --priority 100 --ip-address <cidr>,<cidr>                           # your pod's Tableau Cloud ranges
```
Other `KXTAB_*` settings are app settings too (changing one restarts the app). App Service ends requests
after ~230 s, so keep big archived series within `KXTAB_MAX_MARKETS`. To update, rerun the
`git archive` and `az webapp deploy` lines. In Tableau Cloud use host `<app>.azurewebsites.net`, port 443.

**Azure Container Apps** (the `Dockerfile`; same startup script and HTTP port 8000 as App Service).
Container Apps terminates HTTPS on 443 at `<app>.<env-id>.<region>.azurecontainerapps.io`. From Azure
Cloud Shell (bash), with `ACR` a globally unique registry name (letters and digits only):
```bash
RG=marketpredict; APP=kxtab; ENV=kxtab-env; ACR=<registryname>; LOC=eastus2
git clone https://github.com/dllaird/KX-Tab.git && cd KX-Tab
az acr create -g $RG -n $ACR -l $LOC --sku Basic --admin-enabled true
az acr build -r $ACR -t kxtab:v1 .
az containerapp env create -g $RG -n $ENV -l $LOC --logs-destination none
az containerapp create -g $RG -n $APP --environment $ENV \
  --image $ACR.azurecr.io/kxtab:v1 --registry-server $ACR.azurecr.io \
  --ingress external --target-port 8000 --min-replicas 1 --max-replicas 1 --cpu 1 --memory 2Gi \
  --secrets tabpy-pwd='<password>' \
  --env-vars KXTAB_TICKER=KXNCAAF-27 KXTAB_TABPY_PASSWORD=secretref:tabpy-pwd KXTAB_MAX_MARKETS=500
FQDN=$(az containerapp show -g $RG -n $APP --query properties.configuration.ingress.fqdn -o tsv)
curl -u tableau:'<password>' https://$FQDN/info                                      # expect JSON, not 401
az containerapp ingress access-restriction set -g $RG -n $APP --rule-name tableau-1 \
  --action Allow --ip-address <cidr>                                                 # repeat per Tableau Cloud range
```
Logs: `az containerapp logs show -g $RG -n $APP --follow`. To update: `git pull`, rerun `az acr build`
with a new tag (`kxtab:v2`), then `az containerapp update -g $RG -n $APP --image $ACR.azurecr.io/kxtab:v2`.
`--min-replicas 1` keeps it warm for Tableau; requests time out after ~240 s.

**Tableau Cloud:** Settings > Extensions > Analytics Extensions: enable, add a TabPy connection with
host `<dns-name>`, port 9004 (443 on App Service or Container Apps), SSL on, and the TabPy username/password. Table extensions in workbooks
then run on the server. When several workbooks share one server, pass the ticker in the script:
`return kxtab.history("KXNCAAF-27")`.

## License

MIT. See [LICENSE](LICENSE).
