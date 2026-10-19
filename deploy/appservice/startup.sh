#!/usr/bin/env bash
# Start TabPy for KX-Tab on Azure App Service (Linux, Python).
# Startup command: bash deploy/appservice/startup.sh
# App settings: KXTAB_TICKER, KXTAB_TABPY_PASSWORD, optional KXTAB_TABPY_USER (default tableau).
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"

: "${KXTAB_TICKER:?KXTAB_TICKER app setting is not set}"
: "${KXTAB_TABPY_PASSWORD:?KXTAB_TABPY_PASSWORD app setting is not set}"

# Fallback if the build didn't install TabPy (see PRE_BUILD_COMMAND in the README).
if ! python -c "import tabpy" 2>/dev/null; then
    echo "TabPy not installed by the build; installing requirements-tabpy.txt"
    python -m pip install --quiet -r "$root/requirements-tabpy.txt"
fi

export KXTAB_STATE_DIR="${KXTAB_STATE_DIR:-/tmp/kxtab}"
export KXTAB_PWD_FILE="$KXTAB_STATE_DIR/tabpy_users.txt"
mkdir -p "$KXTAB_STATE_DIR"

# Write TabPy's login file from app settings on every start (same hash as tabpy-user).
python - <<'EOF'
import os
from tabpy.tabpy_server.handlers.util import hash_password
user = os.environ.get("KXTAB_TABPY_USER", "tableau").lower()
with open(os.environ["KXTAB_PWD_FILE"], "w") as f:
    f.write(f"{user} {hash_password(user, os.environ['KXTAB_TABPY_PASSWORD'])}\n")
EOF
chmod 600 "$KXTAB_PWD_FILE"
unset KXTAB_TABPY_PASSWORD   # keep it out of TabPy's environment

export PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}"
conf="$root/deploy/appservice/tabpy.conf"
echo "KXTAB_TICKER=$KXTAB_TICKER -> python -m tabpy.tabpy --config $conf"
exec python -m tabpy.tabpy --config "$conf"
