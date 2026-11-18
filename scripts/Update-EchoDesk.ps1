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
        throw "命令执行失败（退出代码 $LASTEXITCODE）： $Program $($Arguments -join ' ')"
    }
}

function Get-GitOutput {
    param([string[]]$Arguments)
    $output = & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Git 命令执行失败：git $($Arguments -join ' ')"
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
            throw '下载的 uv 安装包未通过 SHA-256 校验。'
        }
        Expand-Archive -LiteralPath $archive -DestinationPath $toolFolder -Force
    }
    return $uvPath
}

try {
    Set-Location -LiteralPath $projectPath
    $null = Get-Command git -CommandType Application -ErrorAction Stop
    if ((Get-GitOutput @('rev-parse', '--show-toplevel')).Replace('/', '\') -ne $projectPath) {
        throw '请在 EchoDesk 仓库内运行此脚本。'
    }
    if ((Get-GitOutput @('branch', '--show-current')) -ne 'master') {
        throw '请切换到 master 分支后再更新。'
    }
    $remoteUrl = Get-GitOutput @('remote', 'get-url', 'origin')
    foreach ($requiredFile in @('main.py', 'requirements.txt', 'pyproject.toml')) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "缺少必需文件：$requiredFile"
        }
    }
    foreach ($state in @('MERGE_HEAD', 'rebase-merge', 'rebase-apply', 'CHERRY_PICK_HEAD')) {
        $statePath = Get-GitOutput @('rev-parse', '--git-path', $state)
        if (Test-Path -LiteralPath $statePath) {
            throw "请先完成当前 Git 操作：$state"
        }
    }

    Write-Host "项目目录：$projectPath"
    Write-Host "更新来源：$remoteUrl（master）"
    if (Get-GitOutput @('status', '--porcelain')) {
        Write-Host '检测到本地修改。如果更新会覆盖这些修改，Git 将停止更新。' -ForegroundColor Yellow
    }
    if ($CheckOnly) {
        if (Test-Path -LiteralPath $pythonPath) {
            Invoke-Checked $pythonPath @('--version')
        } else {
            Write-Host '更新时将创建 Python 3.14.10 虚拟环境。'
        }
        Write-Host '更新预检通过，本次仅执行检查。' -ForegroundColor Green
        exit 0
    }

    # Do not replace DLLs while this environment is in use.
    $venvScripts = Split-Path -Parent $pythonPath
    $running = @(Get-Process -Name python, pythonw -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and (Split-Path -Parent $_.Path) -eq $venvScripts })
    if ($running.Count -gt 0) {
        throw '请先关闭 EchoDesk 和其他正在使用此项目的 Python 进程。'
    }

    $null = New-Item -ItemType Directory -Path (Join-Path $projectPath 'logs') -Force
    $logPath = Join-Path $projectPath ("logs\desktop-update-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    $null = Start-Transcript -Path $logPath
    $transcribing = $true

    Write-Host "`n[1/5] 正在更新代码和受版本控制的资源…"
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
        if ($LASTEXITCODE -eq 0) { throw '此仓库需要 Git LFS，请安装后重试。' }
    }

    Write-Host "`n[2/5] 正在准备项目的 Python 环境…"
    $uvPath = Get-ProjectUv
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $projectPath 'python'
    $requiredPython = (Get-Content -LiteralPath '.python-version' -Raw).Trim()
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        Invoke-Checked $uvPath @('venv', '--python', $requiredPython, '--seed', '--relocatable',
            '--cache-dir', (Join-Path $projectPath 'cache\uv'), (Join-Path $projectPath '.venv'))
    }
    Invoke-Checked $pythonPath @('-c', "import platform, sys; sys.exit(0 if platform.python_version() == '$requiredPython' else '项目需要 Python $requiredPython，请先迁移项目环境。')")

    Write-Host "`n[3/5] 正在更新 Python 包管理工具…"
    Invoke-Checked $uvPath @('pip', 'install', '--python', $pythonPath, '--cache-dir', (Join-Path $projectPath 'cache\uv'),
        '--upgrade', 'pip')

    Write-Host "`n[4/5] 正在安装已锁定版本的运行和开发依赖…"
    Invoke-Checked $pythonPath @('-X', 'utf8', '.github\scripts\install_dependencies.py')

    Write-Host "`n[5/5] 正在检查依赖版本和启动模块导入…"
    Invoke-Checked $pythonPath @('-X', 'utf8', 'scripts\check_dependencies.py')
    Invoke-Checked $pythonPath @('-c', "import ok, PySide6; from src.identity import configure_process_identity; from config import config; print('启动模块导入成功：', config['gui_title'])")
    Write-Host "`n更新完成，可通过桌面快捷方式启动 EchoDesk。" -ForegroundColor Green
}
catch {
    $exitCode = 1
    Write-Host "`n更新已停止：$($_.Exception.Message)" -ForegroundColor Red
}
finally {
    if ($transcribing) { $null = Stop-Transcript }
}

if (-not $NoPause -and -not $CheckOnly) {
    $null = Read-Host 'Press Enter to close'
}
exit $exitCode
