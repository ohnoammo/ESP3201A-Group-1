# STEP 3 (after Claude has written the questions): check them. No GPU, can run during step 2.
# Run:  powershell -ExecutionPolicy Bypass -File .\step3_exp2_check_questions.ps1
. "$PSScriptRoot\_common.ps1"
if (-not (Test-Path "exp2_sympy\questions_src.json")) {
    Write-Host "Claude has not written the questions yet (exp2_sympy\questions_src.json is missing)." -ForegroundColor Yellow
    exit 1
}
Invoke-Step @("exp2_sympy.py", "build") "Check that every quote is word for word in its PR"
Write-Host ""
Write-Host "Now a person checks each question: open exp2_sympy\question_check_sheet.csv, click each PR link," -ForegroundColor Green
Write-Host "and write ok / fix / drop in the 'check' column (about 30 min). Send Claude any fix / drop rows." -ForegroundColor Green
Start-Process "exp2_sympy\question_check_sheet.csv"
