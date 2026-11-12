# STEP 4 (after step 2 has finished AND the questions are checked; before step 2b): run Experiment 2 on SymPy.
# Run:  powershell -ExecutionPolicy Bypass -File .\step4_exp2_run.ps1
. "$PSScriptRoot\_common.ps1"
Write-Host "STEP 4: Experiment 2 on SymPy (GPU, about 30-45 minutes)." -ForegroundColor Green
if (-not (Test-Path "results\swe_exp1_sympy_tuned.json")) {
    Write-Host "Step 2 has not finished yet (no tuned results). Wait for it first." -ForegroundColor Yellow
    exit 1
}
Confirm-Yes "Is the GPU free (step 2 finished and step 2b not running)?"
if (-not (Test-Path "exp2_sympy\questions.jsonl")) {
    Write-Host "Run step 3 first (the questions are not built yet)." -ForegroundColor Yellow
    exit 1
}
Confirm-Yes "Have the questions been checked by a person (step 3) and any fixes sent to Claude?"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Ollama is not installed. Install it from https://ollama.com/download, then run step 4 again." -ForegroundColor Yellow
    exit 1
}
ollama --version
$list = (ollama list) -join "`n"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ollama is installed but not running: open the Ollama app, then run step 4 again." -ForegroundColor Yellow
    exit 1
}
if ($list -notmatch [regex]::Escape($model)) {
    Write-Host "Downloading $model (about 2.5 GB) ..."
    ollama pull $model
    if ($LASTEXITCODE -ne 0) { Write-Host "Model download failed." -ForegroundColor Red; exit 1 }
}
Invoke-Step @("exp2_sympy.py", "retrieve") "Retrieve the top 100 chunks per question (GPU, minutes)"
Invoke-Step @("exp2_sympy.py", "generate") "Generate the answers with the 4B model (about 15-30 min)"
Invoke-Step @("exp2_sympy.py", "score") "Score the answers and make the labelling sheet"
Write-Host ""
Write-Host "STEP 4 DONE. Next: label exp2_sympy\correctness_sheet.csv (rules: exp2_sympy\LABELLING.txt)." -ForegroundColor Green
Write-Host "Do NOT open the exp2_sympy\keys folder before labelling. Then run step 5." -ForegroundColor Green
Start-Process "exp2_sympy\LABELLING.txt"
Start-Process "exp2_sympy\correctness_sheet.csv"
