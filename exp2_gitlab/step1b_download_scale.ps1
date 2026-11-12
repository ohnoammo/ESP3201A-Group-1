# Downloads the scaled Exp 1 pool (231 tasks + 2,000 distractors). Asks for a GitLab token (read_api);
# the token stays in this window only and is not saved. MRs already downloaded are reused.
# Safe to run again: it resumes. Keep the laptop awake and avoid clicking inside this window.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$s = Read-Host "GitLab token (read_api)" -AsSecureString
$env:GITLAB_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
python gitlab_mrs.py pool --tasks 231 --distractors 2000
if ($LASTEXITCODE -ne 0) { Write-Host "STOPPED" -ForegroundColor Red; exit 1 }
python mark_bots.py
if ($LASTEXITCODE -eq 0) { Write-Host "STEP 1B DONE" -ForegroundColor Green } else { Write-Host "STOPPED" -ForegroundColor Red }
