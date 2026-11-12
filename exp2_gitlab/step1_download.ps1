# Downloads the 300-MR pilot pool with its discussions. Asks for a GitLab token (scope read_api);
# the token stays in this window only and is not saved. Safe to run again: it resumes.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$s = Read-Host "GitLab token (read_api)" -AsSecureString
$env:GITLAB_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
python gitlab_mrs.py pool --tasks 30 --distractors 270
if ($LASTEXITCODE -eq 0) { Write-Host "STEP 1 DONE" -ForegroundColor Green } else { Write-Host "STOPPED" -ForegroundColor Red }
