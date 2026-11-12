# STEP 5 (after the correctness sheet is labelled and saved): optional gate + final table.
# Run:  powershell -ExecutionPolicy Bypass -File .\step5_exp2_finish.ps1
. "$PSScriptRoot\_common.ps1"
Write-Host "STEP 5: gate (optional) and final table." -ForegroundColor Green
Confirm-Yes "Is exp2_sympy\correctness_sheet.csv labelled, saved and closed in Excel?"
$g = Read-Host "Run the optional MiniCheck gate? It downloads about 3 GB the first time. Type yes or no"
if ($g -eq "yes") {
    if (Get-Command ollama -ErrorAction SilentlyContinue) { ollama stop $model 2>$null }
    Write-Host ""
    Write-Host "=== MiniCheck gate ===" -ForegroundColor Cyan
    & $py -u exp2_sympy.py gate
    if ($LASTEXITCODE -ne 0) {
        Write-Host "GPU attempt failed (probably not enough memory); trying on the CPU (slower) ..." -ForegroundColor Yellow
        Invoke-Step @("exp2_sympy.py", "gate", "--device", "cpu") "MiniCheck gate on CPU"
    }
}
Invoke-Step @("exp2_sympy.py", "report") "Final table"
Write-Host ""
Write-Host "STEP 5 DONE. Tell Claude: step 5 done." -ForegroundColor Green
