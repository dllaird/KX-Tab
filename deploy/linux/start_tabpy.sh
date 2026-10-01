#!/usr/bin/env bash
# Start TabPy for KX-Tab on Linux.   deploy/linux/start_tabpy.sh [env-file]
# Settings come from the environment (systemd EnvironmentFile) or the optional env file.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"

if [[ $# -ge 1 ]]; then
    set -a; source "$1"; set +a
fi

: "${KXTAB_TICKER:?KXTAB_TICKER is not set (see deploy/kxtab.env.example)}"
tabpy="${KXTAB_TABPY:-$root/.venv/bin/tabpy}"
conf="${KXTAB_TABPY_CONF:-$root/deploy/tabpy-https.conf}"

[[ -x "$tabpy" ]] || { echo "TabPy not found at $tabpy (pip install -r requirements-tabpy.txt, or set KXTAB_TABPY)" >&2; exit 1; }
[[ -f "$conf" ]] || { echo "TabPy config not found: $conf" >&2; exit 1; }
for var in KXTAB_PWD_FILE KXTAB_CERT_FILE KXTAB_KEY_FILE; do
    if grep -qi "%(${var,,})s" "$conf" && [[ ! -r "${!var:-}" ]]; then
        echo "$var is not set or not readable: ${!var:-<unset>}" >&2; exit 1
    fi
done

export PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}"
export TABPY_CONF_DIR="$(dirname "$conf")"
echo "KXTAB_TICKER=$KXTAB_TICKER -> $tabpy --config $conf"
exec "$tabpy" --config "$conf"
