param(
    [switch]$AutoStart
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $RepoRoot ".runtime"
$LogsDir = Join-Path $RepoRoot "logs"
$ServiceScript = Join-Path $RepoRoot "service.py"
$ServiceUrl = "http://127.0.0.1:4332/health"
$AutoStartRegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$AutoStartValueName = "CodexMusicNewsService"
$PowerShellExe = (Get-Command powershell.exe).Source

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$PythonExe = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

function Test-MusicNewsService {
    try {
        $Response = Invoke-WebRequest -Uri $ServiceUrl -UseBasicParsing -TimeoutSec 3
        return $Response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Ensure-MusicNewsAutoStart {
    $RunArgs = @(
        "-NoProfile",
        "-NonInteractive",
        "-WindowStyle", "Hidden",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-AutoStart"
    ) -join " "
    $Command = "`"$PowerShellExe`" $RunArgs"
    New-Item -Path $AutoStartRegPath -Force | Out-Null
    New-ItemProperty -Path $AutoStartRegPath -Name $AutoStartValueName -Value $Command -PropertyType String -Force | Out-Null
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

Push-Location $RepoRoot
try {
    try {
        Ensure-MusicNewsAutoStart
    } catch {
        Write-Warning "MusicNews auto-start registration failed, but current startup will continue."
    }

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
    Pop-Location
}
