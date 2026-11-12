# Shared settings for the step scripts (not run on its own).
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
$py = Join-Path $env:USERPROFILE "anaconda3\envs\esp3201a\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$model = "qwen3:4b-instruct-2507-q4_K_M"
Write-Host "Folder: $PSScriptRoot"
Write-Host "Python: $py"

function Invoke-Step([string[]]$PyArgs, [string]$What) {
    Write-Host ""
    Write-Host "=== $What ===" -ForegroundColor Cyan
    & $py -u @PyArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "STOPPED: '$What' failed (exit code $LASTEXITCODE)." -ForegroundColor Red
        Write-Host "Copy the last lines above (especially any red text) to Claude." -ForegroundColor Red
        exit 1
    }
}

function Confirm-Yes([string]$Question) {
    $a = Read-Host "$Question  Type yes to continue"
    if ($a -ne "yes") { Write-Host "Stopped (nothing was run)."; exit 0 }
}
