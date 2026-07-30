$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName "NEXUS26 Display" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Autostart removed. Theme files remain in %LOCALAPPDATA%\NEXUS26."
