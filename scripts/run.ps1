$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$PythonExe = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "logs") | Out-Null

Push-Location $RepoRoot
try {
    $env:MUSICNEWS_SEND_EMAIL = "1"
    & $PythonExe "main.py"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
} finally {
    Remove-Item Env:\MUSICNEWS_SEND_EMAIL -ErrorAction SilentlyContinue
    Pop-Location
}
