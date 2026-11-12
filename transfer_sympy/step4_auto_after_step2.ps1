# STEP 4 (automatic): run this NOW in a SECOND terminal and go to sleep. It does the quick checks now,
# waits until step 2 has finished, then runs Experiment 2 on SymPy by itself.
# Run:  powershell -ExecutionPolicy Bypass -File .\step4_auto_after_step2.ps1
. "$PSScriptRoot\_common.ps1"
Write-Host "STEP 4 (automatic): checks now, then waits for step 2, then runs Experiment 2." -ForegroundColor Green
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Ollama is not installed, so no automatic run tonight. In the morning: install it from https://ollama.com/download and run step 4." -ForegroundColor Yellow
    exit 1
}
ollama --version
$list = (ollama list) -join "`n"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ollama is installed but not running: open the Ollama app, then run this again." -ForegroundColor Yellow
    exit 1
}
if ($list -notmatch [regex]::Escape($model)) {
    Write-Host "Downloading $model (about 2.5 GB) ..."
    ollama pull $model
    if ($LASTEXITCODE -ne 0) { Write-Host "Model download failed." -ForegroundColor Red; exit 1 }
}
Invoke-Step @("exp2_sympy.py", "build") "Rebuild the questions with Alyssa's fixes (no GPU)"
$done = "results\stats_sympy_short.txt"
Write-Host ""
Write-Host "Checks passed. Waiting for step 2 to finish (checking every 2 minutes). You can go to sleep now." -ForegroundColor Green
while ($true) {
    if (Test-Path $done) {
        $a = (Get-Item $done).Length
        Start-Sleep -Seconds 90
        $b = (Get-Item $done).Length
        if ($a -gt 500 -and $a -eq $b) { break }
    } else {
        Start-Sleep -Seconds 120
    }
}
Write-Host ("Step 2 finished; starting Experiment 2 at " + (Get-Date -Format "HH:mm"))
Invoke-Step @("exp2_sympy.py", "retrieve") "Retrieve the top 100 chunks per question (GPU, minutes)"
Invoke-Step @("exp2_sympy.py", "generate") "Generate the answers with the 4B model"
Invoke-Step @("exp2_sympy.py", "score") "Score the answers and make the labelling sheet"
Write-Host ""
Write-Host ("STEP 4 DONE at " + (Get-Date -Format "HH:mm") + ". Next: label exp2_sympy\correctness_sheet.csv (rules: exp2_sympy\LABELLING.txt), then step 5.") -ForegroundColor Green
