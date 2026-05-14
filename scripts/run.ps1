param(
    [switch]$AutoStart
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $RepoRoot ".runtime"
$LogsDir = Join-Path $RepoRoot "logs"
$ServiceScript = Join-Path $RepoRoot "service.py"
$ServiceUrl = "http://127.0.0.1:4332/health"
$StartupLockPath = Join-Path $RuntimeDir "musicnews_startup.lock"
$AutoStartRegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$AutoStartValueName = "CodexMusicNewsService"
$LegacyTaskName = "Codex-MusicNews-Service"
$PowerShellExe = (Get-Command powershell.exe).Source

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$PythonExe = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
$script:StartupLockHandle = $null

function Test-MusicNewsService {
    try {
        $Response = Invoke-WebRequest -Uri $ServiceUrl -UseBasicParsing -TimeoutSec 3
        return $Response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Ensure-MusicNewsAutoStart {
    $Command = ('"{0}" -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{1}" -AutoStart' -f $PowerShellExe, $PSCommandPath)
    New-Item -Path $AutoStartRegPath -Force | Out-Null
    if (Get-ItemProperty -Path $AutoStartRegPath -Name $AutoStartValueName -ErrorAction SilentlyContinue) {
        Set-ItemProperty -Path $AutoStartRegPath -Name $AutoStartValueName -Value $Command
    } else {
        New-ItemProperty -Path $AutoStartRegPath -Name $AutoStartValueName -Value $Command -PropertyType String -Force | Out-Null
    }
}

function Acquire-MusicNewsStartupLock {
    try {
        $script:StartupLockHandle = [System.IO.File]::Open(
            $StartupLockPath,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
        $Bytes = [System.Text.Encoding]::UTF8.GetBytes(
            "{`"pid`":$PID,`"startedAt`":`"$([DateTime]::Now.ToString('s'))`"}"
        )
        $script:StartupLockHandle.Write($Bytes, 0, $Bytes.Length)
        $script:StartupLockHandle.Flush()
        return $true
    } catch [System.IO.IOException] {
        return $false
    }
}

function Release-MusicNewsStartupLock {
    if ($script:StartupLockHandle) {
        $script:StartupLockHandle.Dispose()
        $script:StartupLockHandle = $null
    }

    Remove-Item $StartupLockPath -Force -ErrorAction SilentlyContinue
}

function Remove-LegacyMusicNewsScheduledTask {
    try {
        $LegacyTask = Get-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue
        if (-not $LegacyTask) {
            return
        }
    } catch {
        return
    }

    try {
        Unregister-ScheduledTask -TaskName $LegacyTaskName -Confirm:$false
        return
    } catch {
    }

    cmd /c "schtasks /delete /tn ""\$LegacyTaskName"" /f >nul 2>nul" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Legacy MusicNews scheduled task still exists. Current startup will continue, but removing that old task may need admin permission."
    }
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

Push-Location $RepoRoot
try {
    if (-not (Acquire-MusicNewsStartupLock)) {
        for ($WaitIndex = 0; $WaitIndex -lt 30; $WaitIndex += 1) {
            if (Test-MusicNewsService) {
                if ($AutoStart) {
                    Write-Output "MusicNews scheduler auto-start check finished."
                } else {
                    Write-Output "MusicNews scheduler is already starting or online."
                }
                return
            }

            if (-not (Test-Path $StartupLockPath)) {
                break
            }

            Start-Sleep -Seconds 1
        }

        if (Test-MusicNewsService) {
            if ($AutoStart) {
                Write-Output "MusicNews scheduler auto-start check finished."
            } else {
                Write-Output "MusicNews scheduler is already starting or online."
            }
            return
        }

        throw "Another MusicNews startup is still in progress."
    }

    try {
        Ensure-MusicNewsAutoStart
    } catch {
        Write-Warning "MusicNews auto-start registration failed, but current startup will continue."
    }

    Remove-LegacyMusicNewsScheduledTask

    if (-not (Test-MusicNewsService)) {
        $StdOutLog = Join-Path $RuntimeDir "service.stdout.log"
        $StdErrLog = Join-Path $RuntimeDir "service.stderr.log"

        Start-Process `
            -FilePath $PythonExe `
            -ArgumentList @($ServiceScript) `
            -WorkingDirectory $RepoRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $StdOutLog `
            -RedirectStandardError $StdErrLog | Out-Null
    }

    $Ready = $false
    for ($Index = 0; $Index -lt 20; $Index += 1) {
        if (Test-MusicNewsService) {
            $Ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }

    if (-not $Ready) {
        throw "MusicNews background service did not become healthy in time."
    }

    if ($AutoStart) {
        Write-Output "MusicNews scheduler auto-start check finished."
    } else {
        Write-Output "MusicNews scheduler is online. Daily auto-send mode is active."
    }
} finally {
    Release-MusicNewsStartupLock
    Pop-Location
}
