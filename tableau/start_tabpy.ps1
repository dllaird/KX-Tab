# Start TabPy for KX-Tab.
#   .\tableau\start_tabpy.ps1 [-Ticker KXNCAAF-27] [-TabPy C:\path\to\tabpy.exe] [-Config <tabpy.conf>] [-EnvFile <kxtab.env>]
# TabPy: -TabPy, else $env:KXTAB_TABPY, else .venv\Scripts\tabpy.exe, else tabpy on PATH.
# Config: -Config, else $env:KXTAB_TABPY_CONF, else tableau\tabpy.conf (local HTTP). Servers: deploy\tabpy-https.conf.
param([string]$Ticker, [string]$TabPy, [string]$Config, [string]$EnvFile)
$here = $PSScriptRoot
$root = Split-Path -Parent $here

if ($EnvFile) {
    foreach ($line in Get-Content $EnvFile) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') { Set-Item "env:$($Matches[1])" $Matches[2] }
    }
}
if ($Ticker) { $env:KXTAB_TICKER = $Ticker }
if (-not $env:KXTAB_TICKER) {
    Write-Host "KXTAB_TICKER is not set. Pass -Ticker <ticker>, -EnvFile <file>, or run: setx KXTAB_TICKER <ticker>."
    exit 1
}

$candidates = @($TabPy, $env:KXTAB_TABPY, (Join-Path $root ".venv\Scripts\tabpy.exe")) | Where-Object { $_ -and (Test-Path $_) }
$exe = if ($candidates) { @($candidates)[0] } else { (Get-Command tabpy -ErrorAction SilentlyContinue).Source }
if (-not $exe) {
    Write-Host "TabPy not found. Pass -TabPy <path>, set KXTAB_TABPY, or: .venv\Scripts\pip install -r requirements-tabpy.txt"
    exit 1
}

$conf = @($Config, $env:KXTAB_TABPY_CONF, (Join-Path $here "tabpy.conf")) | Where-Object { $_ } | Select-Object -First 1
if (-not (Test-Path $conf)) { Write-Host "TabPy config not found: $conf"; exit 1 }
$confDir = Split-Path -Parent (Resolve-Path $conf)
$text = Get-Content $conf -Raw
$users = if ($text -match 'tabpy_conf_dir') { Join-Path $confDir "tabpy_users.txt" } else { $env:KXTAB_PWD_FILE }
if (-not $users -or -not (Test-Path $users)) {
    $tool = Join-Path (Split-Path -Parent $exe) "tabpy-user.exe"
    Write-Host "No TabPy user file. Run: & `"$tool`" add -u tableau -p <password> -f `"$(if ($users) { $users } else { '<KXTAB_PWD_FILE>' })`""
    exit 1
}
foreach ($name in @("KXTAB_CERT_FILE", "KXTAB_KEY_FILE")) {
    $path = [Environment]::GetEnvironmentVariable($name)
    if ($text -match $name.ToLower() -and (-not $path -or -not (Test-Path $path))) {
        Write-Host "$name is not set or the file is missing: $path"
        exit 1
    }
}

$env:PYTHONPATH = $root + $(if ($env:PYTHONPATH) { ";" + $env:PYTHONPATH } else { "" })
$env:TABPY_CONF_DIR = $confDir
Write-Host "KXTAB_TICKER=$env:KXTAB_TICKER  ->  $exe --config $conf"
& $exe --config $conf
