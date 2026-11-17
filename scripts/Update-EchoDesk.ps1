param(
    [switch]$CheckOnly,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
$exitCode = 0
$transcribing = $false

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $Program $($Arguments -join ' ')"
    }
}

function Get-GitOutput {
    param([string[]]$Arguments)
    $output = & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git failed: git $($Arguments -join ' ')"
    }
    return ($output -join "`n").Trim()
}

function Get-ProjectUv {
    $uvPin = (Select-String -LiteralPath (Join-Path $projectPath 'requirements-dev.txt') -Pattern '^uv==').Line
    $uvVersion = ($uvPin -split '==')[1].Trim()
    $toolFolder = Join-Path $projectPath "cache\tools\uv-$uvVersion"
    $uvPath = Join-Path $toolFolder "uv-$uvVersion.data\scripts\uv.exe"
    if (-not (Test-Path -LiteralPath $uvPath -PathType Leaf)) {
        $null = New-Item -ItemType Directory -Path $toolFolder -Force
        $release = Invoke-RestMethod "https://pypi.org/pypi/uv/$uvVersion/json"
        $wheel = $release.urls | Where-Object { $_.filename -like '*-win_amd64.whl' } | Select-Object -First 1
        $archive = Join-Path $toolFolder 'uv.zip'
        Invoke-WebRequest -Uri $wheel.url -OutFile $archive
        if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $wheel.digests.sha256) {
            throw 'Downloaded uv wheel failed its SHA-256 verification.'
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $toolFolder -Force
    }
    return $uvPath
}

try {
    Set-Location -LiteralPath $projectPath
    $null = Get-Command git -CommandType Application -ErrorAction Stop
    if ((Get-GitOutput @('rev-parse', '--show-toplevel')).Replace('/', '\') -ne $projectPath) {
        throw 'The script must be inside the EchoDesk repository.'
    }
    if ((Get-GitOutput @('branch', '--show-current')) -ne 'master') {
        throw 'Switch to master before updating. No branch was changed.'
    }
    $remoteUrl = Get-GitOutput @('remote', 'get-url', 'origin')
    foreach ($requiredFile in @('main.py', 'requirements.txt', 'pyproject.toml')) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "Missing required file: $requiredFile"
        }
    }
    foreach ($state in @('MERGE_HEAD', 'rebase-merge', 'rebase-apply', 'CHERRY_PICK_HEAD')) {
        $statePath = Get-GitOutput @('rev-parse', '--git-path', $state)
        if (Test-Path -LiteralPath $statePath) {
            throw "Finish the current Git operation first: $state"
        }
    }

    Write-Host "Repository: $projectPath"
    Write-Host "Update source: $remoteUrl (master)"
    if (Get-GitOutput @('status', '--porcelain')) {
        Write-Host 'Local changes detected. Git will stop if an update would overwrite them.' -ForegroundColor Yellow
    }
    if ($CheckOnly) {
        if (Test-Path -LiteralPath $pythonPath) {
            Invoke-Checked $pythonPath @('--version')
        } else {
            Write-Host 'A Python 3.14.10 virtual environment will be created during the update.'
        }
        Write-Host 'Update preflight passed. No files or dependencies were changed.' -ForegroundColor Green
        exit 0
    }

    # Do not replace DLLs while this environment is in use.
    $venvScripts = Split-Path -Parent $pythonPath
    $running = @(Get-Process -Name python, pythonw -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and (Split-Path -Parent $_.Path) -eq $venvScripts })
    if ($running.Count -gt 0) {
        throw 'Close EchoDesk and other Python processes using this project before updating.'
    }

    $null = New-Item -ItemType Directory -Path (Join-Path $projectPath 'logs') -Force
    $logPath = Join-Path $projectPath ("logs\desktop-update-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $null = Start-Transcript -Path $logPath
    $transcribing = $true

    Write-Host "`n[1/5] Updating code and tracked assets..."
    Invoke-Checked git @('fetch', '--prune', '--tags', 'origin')
    # Disable autostash even if globally enabled; never hide or discard local work.
    Invoke-Checked git @('-c', 'merge.autoStash=false', 'merge', '--ff-only', 'refs/remotes/origin/master')
    if (Test-Path -LiteralPath '.gitmodules') {
        Invoke-Checked git @('submodule', 'sync', '--recursive')
        Invoke-Checked git @('submodule', 'update', '--init', '--recursive')
    }
    & git lfs version *> $null
    if ($LASTEXITCODE -eq 0) {
        Invoke-Checked git @('lfs', 'pull', 'origin', 'master')
    } else {
        & git grep --quiet 'filter=lfs' -- '*.gitattributes'
        if ($LASTEXITCODE -eq 0) { throw 'This repository needs Git LFS. Install Git LFS and retry.' }
    }

    Write-Host "`n[2/5] Preparing the project Python environment..."
    $uvPath = Get-ProjectUv
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $projectPath 'python'
    $requiredPython = (Get-Content -LiteralPath '.python-version' -Raw).Trim()
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        Invoke-Checked $uvPath @('venv', '--python', $requiredPython, '--seed', '--relocatable',
            '--cache-dir', (Join-Path $projectPath 'cache\uv'), (Join-Path $projectPath '.venv'))
    }
    Invoke-Checked $pythonPath @('-c', "import platform, sys; sys.exit(0 if platform.python_version() == '$requiredPython' else 'Expected Python $requiredPython; migrate the project environment before updating.')")

    Write-Host "`n[3/5] Updating Python package tools..."
    Invoke-Checked $uvPath @('pip', 'install', '--python', $pythonPath, '--cache-dir', (Join-Path $projectPath 'cache\uv'),
        '--upgrade', 'pip')

    Write-Host "`n[4/5] Installing locked runtime and development dependencies..."
    Invoke-Checked $pythonPath @('-X', 'utf8', '.github\scripts\install_dependencies.py')

    Write-Host "`n[5/5] Checking dependency consistency and startup imports..."
    Invoke-Checked $pythonPath @('-X', 'utf8', 'scripts\check_dependencies.py')
    Invoke-Checked $pythonPath @('-c', "import ok, PySide6; from src.identity import configure_process_identity; from config import config; print('Startup imports OK:', config['gui_title'])")
    Write-Host "`nUpdate complete. Use the desktop launch shortcut to start EchoDesk." -ForegroundColor Green
}
catch {
    $exitCode = 1
    Write-Host "`nUpdate stopped: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
    if ($transcribing) { $null = Stop-Transcript }
}

if (-not $NoPause -and -not $CheckOnly) {
    $null = Read-Host 'Press Enter to close'
}
exit $exitCode
