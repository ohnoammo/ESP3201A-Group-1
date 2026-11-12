# STEP 2 (Wednesday): Experiment 1 on SymPy, TUNED run (Django's locked settings). GPU, ~4-5 hours.
# The untuned run is step 2b (run it after step 4, e.g. overnight).
# Run:  powershell -ExecutionPolicy Bypass -File .\step2_exp1_runs.ps1
. "$PSScriptRoot\_common.ps1"
Write-Host "STEP 2: Experiment 1 on SymPy, tuned run (GPU, about 4-5 hours; saved embeddings are reused)." -ForegroundColor Green
Write-Host "Before starting: pause Windows Update (1 week), plug in the charger, set sleep to Never, pause OneDrive."
Confirm-Yes "Ready?"
$pool = @("--repo", "sympy/sympy", "--split", "all", "--pool", "A", "--n-distractors", "2000")
# Django's locked pool A settings (agreed 22 Oct), applied unchanged
$tuned = @("--fixed-sizes", "512", "--overlap-fracs", "0.1504", "--struct-caps", "256",
           "--fixed-k1b", "1.2", "0.75", "--struct-k1b", "1.2", "0.75",
           "--alpha-map", "fixed.bm25=0", "fixed.dense=1", "fixed.hybrid=0.5",
           "structural.bm25=0", "structural.dense=0.5", "structural.hybrid=0",
           "--size-matched", "--query-sets", "full", "short", "--batch-size", "16")
Invoke-Step (@("run_retrieval_swe.py") + $pool + @("--max-tasks", "5", "--retrievers", "bm25",
    "--fixed-sizes", "512", "--overlap-fracs", "0.1504", "--struct-caps", "256", "--tag", "_sympy_pilot")) "Quick check: 5 tasks, BM25 only (minutes)"
Invoke-Step (@("run_retrieval_swe.py") + $pool + $tuned + @("--tag", "_sympy_tuned")) "Tuned run: Django's locked settings (longest part)"
Write-Host ""
Write-Host "=== Statistics (tuned run only; step 2b adds tuned vs untuned) ===" -ForegroundColor Cyan
& $py stats.py results\swe_exp1_sympy_tuned_per_query.csv | Out-File -Encoding utf8 results\stats_sympy_tuned_full.txt
& $py stats.py results\swe_exp1_sympy_tuned_per_query.csv --short | Out-File -Encoding utf8 results\stats_sympy_tuned_short.txt
Write-Host "Saved results\stats_sympy_tuned_full.txt and results\stats_sympy_tuned_short.txt"
Write-Host ""
Write-Host "STEP 2 DONE. Next: step 4 (Experiment 2), then step 2b (untuned run) overnight. Tell Claude: step 2 done." -ForegroundColor Green
