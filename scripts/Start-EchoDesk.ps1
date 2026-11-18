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
            throw "缺少文件：$requiredFile。请先运行桌面上的更新快捷方式。"
        }
    }
    if ($CheckOnly) {
        & $pythonPath -c "import ok, PySide6; from src.identity import configure_process_identity; from config import config; print('启动模块导入成功：', config['gui_title'])"
        if ($LASTEXITCODE -ne 0) { throw '启动模块导入检查失败，请运行桌面上的更新快捷方式。' }
        Write-Host '启动预检通过，本次仅执行检查。' -ForegroundColor Green
    } else {
        # Reuse the repository launcher for UAC, logging and the project virtualenv.
        & $launcherPath -EntryPoint 'main.py'
        if ($LASTEXITCODE -ne 0) { throw "EchoDesk 已退出，退出代码为 $LASTEXITCODE。请查看 logs\echodesk.log。" }
    }
}
catch {
    $exitCode = 1
    Write-Host "`n启动失败：$($_.Exception.Message)" -ForegroundColor Red
    if (-not $NoPause -and -not $CheckOnly) {
        $null = Read-Host 'Press Enter to close'
    }
}
exit $exitCode
