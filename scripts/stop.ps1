$ErrorActionPreference = "Stop"

$AutoStartRegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$AutoStartValueName = "CodexMusicNewsService"
$Targets = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq "python.exe" -or $_.Name -eq "pythonw.exe") -and
    $_.CommandLine -like "*service.py*"
}

try {
    if (Get-ItemProperty -Path $AutoStartRegPath -Name $AutoStartValueName -ErrorAction SilentlyContinue) {
        Remove-ItemProperty -Path $AutoStartRegPath -Name $AutoStartValueName -Force -ErrorAction Stop
    }
} catch {
}

if (-not $Targets) {
    Write-Output "MusicNews scheduler is already stopped"
    return
}

$Targets | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
}

Write-Output "MusicNews scheduler stopped"
