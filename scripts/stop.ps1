$ErrorActionPreference = "Stop"

$Targets = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "python.exe" -and
    $_.CommandLine -like "*MusicNews*main.py*"
}

if (-not $Targets) {
    Write-Output "MusicNews is not running"
    return
}

$Targets | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
}

Write-Output "MusicNews stopped"
