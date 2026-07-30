$ErrorActionPreference = "Stop"

$ThemeDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$InstallDir = Join-Path $env:LOCALAPPDATA "NEXUSMINIMAL"
$Python = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "py" }

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Path (Join-Path $ThemeDir "*") -Destination $InstallDir -Recurse -Force
& $Python -3 -m venv (Join-Path $InstallDir ".venv")
$VenvPython = Join-Path $InstallDir ".venv\Scripts\pythonw.exe"
$VenvConsole = Join-Path $InstallDir ".venv\Scripts\python.exe"
& $VenvConsole -m pip install --upgrade pip
& $VenvConsole -m pip install -r (Join-Path $InstallDir "requirements-portable.txt")

$Action = New-ScheduledTaskAction `
    -Execute $VenvPython `
    -Argument "-m nexusminimal --config `"$InstallDir\config.yaml`"" `
    -WorkingDirectory $InstallDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
Stop-ScheduledTask -TaskName "NEXUS26 Display" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "NEXUS26 Display" -Confirm:$false -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName "TRUEVIEW26 Display" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "TRUEVIEW26 Display" -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "NEXUSMINIMAL Display" -Action $Action -Trigger $Trigger -Settings $Settings -Force | Out-Null
Start-ScheduledTask -TaskName "NEXUSMINIMAL Display"
Write-Host "NEXUS MINIMAL installed and started from $InstallDir"
