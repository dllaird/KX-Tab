# Run KX-Tab's TabPy at startup on a Windows server (Task Scheduler, restarts on failure). Run as Administrator:
#   .\deploy\windows\register_task.ps1 -EnvFile C:\kxtab\kxtab.env [-TabPy C:\path\to\tabpy.exe] [-AllowFrom 1.2.3.0/24,5.6.7.8]
param(
    [Parameter(Mandatory)][string]$EnvFile,
    [string]$TabPy,
    [string]$Config,
    [string[]]$AllowFrom,          # Tableau Cloud IP ranges for your pod; opens TCP 9004 only to these
    [string]$TaskName = "KX-Tab TabPy"
)
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $Config) { $Config = Join-Path $root "deploy\tabpy-https.conf" }
$launcher = Join-Path $root "tableau\start_tabpy.ps1"
$run = "& '$launcher' -EnvFile '$EnvFile' -Config '$Config'" + $(if ($TabPy) { " -TabPy '$TabPy'" } else { "" })
# Loop so TabPy comes back if it exits (Task Scheduler's own restart only covers failures to start).
$taskArgs = "-NoProfile -ExecutionPolicy Bypass -Command `"while (`$true) { $run; Start-Sleep -Seconds 5 }`""

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $taskArgs -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Registered '$TaskName'. Start now with: Start-ScheduledTask -TaskName '$TaskName'"

if ($AllowFrom) {
    New-NetFirewallRule -DisplayName "KX-Tab TabPy 9004" -Direction Inbound -Protocol TCP -LocalPort 9004 `
        -RemoteAddress $AllowFrom -Action Allow | Out-Null
    Write-Host "Firewall: TCP 9004 allowed from $($AllowFrom -join ', ')"
}
