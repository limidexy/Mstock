#requires -Version 7.0
# 恢复隔离研究环境，不启动联网选票、计划任务或交易。
param([switch]$RunTests, [string]$Wheelhouse)
$ErrorActionPreference = 'Stop'
$previousUTF8 = $env:PYTHONUTF8
$env:PYTHONUTF8 = '1'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    & py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)"
    if ($LASTEXITCODE -ne 0) { throw '请先安装64位Python 3.12，并确保py启动器可用。' }
    $python = Join-Path $root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        & py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败。' }
    }
    & $python -c "import sys; assert sys.version_info[:2] == (3, 12)"
    if ($LASTEXITCODE -ne 0) { throw '已有虚拟环境版本不符，请人工保留并改名后再重建，脚本不会覆盖。' }
    if ($Wheelhouse) {
        if (-not (Test-Path -LiteralPath $Wheelhouse -PathType Container)) {
            throw '离线依赖包目录不存在。'
        }
        & $python -m pip install --no-index --find-links $Wheelhouse -r requirements-windows-lock.txt
    } else {
        & $python -m pip install -r requirements-windows-lock.txt
    }
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络或代理，禁止关闭证书校验。' }
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) { throw '依赖一致性检查失败。' }
    if ($RunTests) {
        & $python -m pytest
        if ($LASTEXITCODE -ne 0) { throw '测试未通过，请查看测试结果。' }
    }
    Write-Output '隔离研究环境恢复完成；未启用联网流程、自动任务或真实交易。'
} finally {
    $env:PYTHONUTF8 = $previousUTF8
    Pop-Location
}
