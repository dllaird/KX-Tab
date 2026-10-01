# Start TabPy for KX-Tab.   .\tableau\start_tabpy.ps1 [-Ticker KXNCAAF-27] [-TabPy C:\path\to\tabpy.exe]
# Uses -TabPy, else $env:KXTAB_TABPY, else .venv\Scripts\tabpy.exe, else tabpy on PATH.
param([string]$Ticker, [string]$TabPy)
$here = $PSScriptRoot
$root = Split-Path -Parent $here
$users = Join-Path $here "tabpy_users.txt"

if ($Ticker) { $env:KXTAB_TICKER = $Ticker }
if (-not $env:KXTAB_TICKER) {
    Write-Host "KXTAB_TICKER is not set. Pass -Ticker <ticker> or run: setx KXTAB_TICKER <ticker> (then open a new shell)."
    exit 1
}

$candidates = @($TabPy, $env:KXTAB_TABPY, (Join-Path $root ".venv\Scripts\tabpy.exe")) | Where-Object { $_ -and (Test-Path $_) }
$exe = if ($candidates) { @($candidates)[0] } else { (Get-Command tabpy -ErrorAction SilentlyContinue).Source }
if (-not $exe) {
    Write-Host "TabPy not found. Pass -TabPy <path>, set KXTAB_TABPY, or: .venv\Scripts\pip install -r requirements-tabpy.txt"
    exit 1
}
if (-not (Test-Path $users)) {
    $user = Join-Path (Split-Path -Parent $exe) "tabpy-user.exe"
    Write-Host "No TabPy user. Run: & `"$user`" add -u tableau -p <password> -f `"$users`""
    exit 1
}

$env:PYTHONPATH = $root + $(if ($env:PYTHONPATH) { ";" + $env:PYTHONPATH } else { "" })
$env:TABPY_CONF_DIR = $here
Write-Host "KXTAB_TICKER=$env:KXTAB_TICKER  ->  $exe on http://localhost:9004"
& $exe --config (Join-Path $here "tabpy.conf")
