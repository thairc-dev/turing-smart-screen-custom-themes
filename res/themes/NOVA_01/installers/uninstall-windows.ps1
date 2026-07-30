$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName "TRUEVIEW26 Display" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Autostart removed. Theme files remain in %LOCALAPPDATA%\TRUEVIEW26."
