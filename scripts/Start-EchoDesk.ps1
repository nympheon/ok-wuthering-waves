param(
    [switch]$CheckOnly,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
$launcherPath = Join-Path $projectPath '.codex\run.ps1'
$exitCode = 0

try {
    Set-Location -LiteralPath $projectPath
    foreach ($requiredFile in @($pythonPath, $launcherPath, (Join-Path $projectPath 'main.py'))) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "Missing: $requiredFile. Run the desktop update shortcut first."
        }
    }
    if ($CheckOnly) {
        & $pythonPath -c "import ok, PySide6; from src.identity import configure_process_identity; from config import config; print('Startup imports OK:', config['gui_title'])"
        if ($LASTEXITCODE -ne 0) { throw 'Startup import check failed. Run the desktop update shortcut.' }
        Write-Host 'Launch preflight passed. The application was not started.' -ForegroundColor Green
    } else {
        # Reuse the repository launcher for UAC, logging and the project virtualenv.
        & $launcherPath -EntryPoint 'main.py'
        if ($LASTEXITCODE -ne 0) { throw "EchoDesk exited with code $LASTEXITCODE. See logs\echodesk.log." }
    }
}
catch {
    $exitCode = 1
    Write-Host "`nLaunch failed: $($_.Exception.Message)" -ForegroundColor Red
    if (-not $NoPause -and -not $CheckOnly) {
        $null = Read-Host 'Press Enter to close'
    }
}
exit $exitCode
