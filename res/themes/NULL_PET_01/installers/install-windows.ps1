# NULL_PET_01 Windows Installer
$ErrorActionPreference = "Stop"

$ThemeDir = Split-Path -Path $PSScriptRoot -Parent
$AppDir = Join-Path $env:APPDATA "NULLPET01"

if (!(Test-Path $AppDir)) {
    New-Item -ItemType Directory -Path $AppDir | Out-Null
}

Copy-Item -Path (Join-Path $ThemeDir "nullpet01") -Destination $AppDir -Recurse -Force
Copy-Item -Path (Join-Path $ThemeDir "requirements-portable.txt") -Destination $AppDir -Force

$VenvDir = Join-Path $AppDir ".venv"
if (!(Test-Path $VenvDir)) {
    python -m venv $VenvDir
}

$PipExe = Join-Path $VenvDir "Scripts\pip.exe"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"

& $PipExe install --quiet -r (Join-Path $AppDir "requirements-portable.txt")

$TaskName = "NULLPET01_Display"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "-m nullpet01" -WorkingDirectory $AppDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "NULL_PET_01 installed and started successfully on Windows!"
