$ErrorActionPreference = "Stop"

$AutoStartRegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$AutoStartValueName = "CodexMusicNewsService"
$LegacyTaskName = "Codex-MusicNews-Service"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $RepoRoot ".runtime"
$StartupLockPath = Join-Path $RuntimeDir "musicnews_startup.lock"
$ServiceLockPath = Join-Path $RuntimeDir "musicnews_service.lock"
$Targets = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq "python.exe" -or $_.Name -eq "pythonw.exe") -and
    $_.CommandLine -like "*MusicNews*service.py*"
}

try {
    if (Get-ItemProperty -Path $AutoStartRegPath -Name $AutoStartValueName -ErrorAction SilentlyContinue) {
        Remove-ItemProperty -Path $AutoStartRegPath -Name $AutoStartValueName -Force -ErrorAction Stop
    }
} catch {
}

try {
    $LegacyTask = Get-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue
    if ($LegacyTask) {
        try {
            Unregister-ScheduledTask -TaskName $LegacyTaskName -Confirm:$false
        } catch {
            cmd /c "schtasks /delete /tn ""\$LegacyTaskName"" /f >nul 2>nul" | Out-Null
        }
    }
} catch {
}

Remove-Item $StartupLockPath -Force -ErrorAction SilentlyContinue
Remove-Item $ServiceLockPath -Force -ErrorAction SilentlyContinue

if (-not $Targets) {
    Write-Output "MusicNews scheduler is already stopped"
    return
}

$Targets | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
}

Write-Output "MusicNews scheduler stopped"
