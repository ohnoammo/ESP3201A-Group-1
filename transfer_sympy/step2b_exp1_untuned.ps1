# STEP 2b (after step 4, e.g. overnight): Experiment 1 on SymPy, UNTUNED run + statistics. GPU, ~7-9 hours.
# Run:  powershell -ExecutionPolicy Bypass -File .\step2b_exp1_untuned.ps1
. "$PSScriptRoot\_common.ps1"
Write-Host "STEP 2b: Experiment 1 on SymPy, untuned run (GPU, about 7-9 hours)." -ForegroundColor Green
if (-not (Test-Path "results\swe_exp1_sympy_tuned.json")) {
    Write-Host "Run step 2 first (no tuned results yet)." -ForegroundColor Yellow
    exit 1
}
Write-Host "Before starting: Windows Update paused, charger in, sleep = Never, OneDrive paused. Don't start step 4 while this runs."
Confirm-Yes "Ready?"
$pool = @("--repo", "sympy/sympy", "--split", "all", "--pool", "A", "--n-distractors", "2000")
Invoke-Step (@("run_retrieval_swe.py") + $pool + @("--size-matched", "--query-sets", "full", "short",
    "--batch-size", "16", "--tag", "_sympy_untuned")) "Untuned run: default settings"
Write-Host ""
Write-Host "=== Statistics ===" -ForegroundColor Cyan
& $py stats.py results\swe_exp1_sympy_tuned_per_query.csv results\swe_exp1_sympy_untuned_per_query.csv | Out-File -Encoding utf8 results\stats_sympy_full.txt
& $py stats.py results\swe_exp1_sympy_tuned_per_query.csv results\swe_exp1_sympy_untuned_per_query.csv --short | Out-File -Encoding utf8 results\stats_sympy_short.txt
Write-Host "Saved results\stats_sympy_full.txt and results\stats_sympy_short.txt"
Write-Host ""
Write-Host "STEP 2b DONE. Tell Claude: step 2b done." -ForegroundColor Green
