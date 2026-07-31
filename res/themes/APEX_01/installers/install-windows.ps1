# Installer for APEX 01 Theme (Windows PowerShell)
$ErrorActionPreference = "Stop"

$ThemeName = "APEX_01"
$ScriptDir = Resolve-Path "$PSScriptRoot\.."
$PythonExec = (Get-Command python).Source

Write-Host "🚀 Installing $ThemeName for Windows..." -ForegroundColor Cyan

$TaskName = "TURZX_$ThemeName"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action = New-ScheduledTaskAction -Execute $PythonExec -Argument "`"$ScriptDir\run_apex01.py`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings
Start-ScheduledTask -TaskName $TaskName

Write-Host "✅ $ThemeName installed and scheduled to run at logon!" -ForegroundColor Green
