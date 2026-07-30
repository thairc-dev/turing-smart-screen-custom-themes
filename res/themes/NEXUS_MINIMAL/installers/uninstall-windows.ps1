$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName "NEXUSMINIMAL Display" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Autostart removed. Theme files remain in %LOCALAPPDATA%\NEXUSMINIMAL."
